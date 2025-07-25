#!/usr/bin/env python3

import torch
from linear_operator.operators import KroneckerProductLinearOperator

from gpytorch.kernels.rbf_kernel import postprocess_rbf, RBFKernel


class RBFKernelGrad(RBFKernel):
    r"""
    Computes a covariance matrix of the RBF kernel that models the covariance
    between the values and partial derivatives for inputs :math:`\mathbf{x_1}`
    and :math:`\mathbf{x_2}`.

    See :class:`qpytorch.kernels.Kernel` for descriptions of the lengthscale options.

    .. note::

        This kernel does not have an `outputscale` parameter. To add a scaling parameter,
        decorate this kernel with a :class:`gpytorch.kernels.ScaleKernel`.

    :param ard_num_dims: Set this if you want a separate lengthscale for each input
        dimension. It should be `d` if x1 is a `n x d` matrix. (Default: `None`.)
    :param batch_shape: Set this if you want a separate lengthscale for each batch of input
        data. It should be :math:`B_1 \times \ldots \times B_k` if :math:`\mathbf x1` is
        a :math:`B_1 \times \ldots \times B_k \times N \times D` tensor.
    :param active_dims: Set this if you want to compute the covariance of only
        a few input dimensions. The ints corresponds to the indices of the
        dimensions. (Default: `None`.)
    :param lengthscale_prior: Set this if you want to apply a prior to the
        lengthscale parameter. (Default: `None`)
    :param lengthscale_constraint: Set this if you want to apply a constraint
        to the lengthscale parameter. (Default: `Positive`.)
    :param eps: The minimum value that the lengthscale can take (prevents
        divide by zero errors). (Default: `1e-6`.)

    :ivar torch.Tensor lengthscale: The lengthscale parameter. Size/shape of parameter depends on the
        ard_num_dims and batch_shape arguments.

    Example:
        >>> x = torch.randn(10, 5)
        >>> # Non-batch: Simple option
        >>> covar_module = qpytorch.kernels.ScaleKernel(qpytorch.kernels.RBFKernelGrad())
        >>> covar = covar_module(x)  # Output: LinearOperator of size (60 x 60), where 60 = n * (d + 1)
        >>>
        >>> batch_x = torch.randn(2, 10, 5)
        >>> # Batch: Simple option
        >>> covar_module = qpytorch.kernels.ScaleKernel(qpytorch.kernels.RBFKernelGrad())
        >>> # Batch: different lengthscale for each batch
        >>> covar_module = qpytorch.kernels.ScaleKernel(qpytorch.kernels.RBFKernelGrad(batch_shape=torch.Size([2])))
        >>> covar = covar_module(x)  # Output: LinearOperator of size (2 x 60 x 60)
    """

    def __init__(self, **kwargs):
        super(RBFKernelGrad, self).__init__(**kwargs)
        self._interleaved = kwargs.pop('interleaved', True)

    def forward(self, x1, x2, diag=False, **params):
        batch_shape = x1.shape[:-2]
        n_batch_dims = len(batch_shape)
        n1, d = x1.shape[-2:]
        n2 = x2.shape[-2]

        if not diag:
            K = torch.zeros(*batch_shape, n1 * (d + 1), n2 * (d + 1), device=x1.device, dtype=x1.dtype)

            # Scale the inputs by the lengthscale (for stability)
            x1_ = x1.div(self.lengthscale)
            x2_ = x2.div(self.lengthscale)

            # Form all possible rank-1 products for the gradient and Hessian blocks
            outer = x1_.view(*batch_shape, n1, 1, d) - x2_.view(*batch_shape, 1, n2, d)
            outer = outer / self.lengthscale.unsqueeze(-2)
            outer = torch.transpose(outer, -1, -2).contiguous()

            # 1) Kernel block
            diff = self.covar_dist(x1_, x2_, square_dist=True, **params)
            K_11 = postprocess_rbf(diff)
            K[..., :n1, :n2] = K_11

            # 2) First gradient block
            outer1 = outer.view(*batch_shape, n1, n2 * d)
            K[..., :n1, n2:] = outer1 * K_11.repeat([*([1] * (n_batch_dims + 1)), d])

            # 3) Second gradient block
            outer2 = outer.transpose(-1, -3).reshape(*batch_shape, n2, n1 * d)
            outer2 = outer2.transpose(-1, -2)
            K[..., n1:, :n2] = -outer2 * K_11.repeat([*([1] * n_batch_dims), d, 1])

            # 4) Hessian block
            outer3 = outer1.repeat([*([1] * n_batch_dims), d, 1]) * outer2.repeat([*([1] * (n_batch_dims + 1)), d])
            kp = KroneckerProductLinearOperator(
                torch.eye(d, d, device=x1.device, dtype=x1.dtype).repeat(*batch_shape, 1, 1) / self.lengthscale.pow(2),
                torch.ones(n1, n2, device=x1.device, dtype=x1.dtype).repeat(*batch_shape, 1, 1),
            )
            chain_rule = kp.to_dense() - outer3
            K[..., n1:, n2:] = chain_rule * K_11.repeat([*([1] * n_batch_dims), d, d])

            # Symmetrize for stability
            if n1 == n2 and torch.eq(x1, x2).all():
                K = 0.5 * (K.transpose(-1, -2) + K)

            # Apply a perfect shuffle permutation to match the MutiTask ordering
            if self._interleaved:
                pi1 = torch.arange(n1 * (d + 1)).view(d + 1, n1).t().reshape((n1 * (d + 1)))
                pi2 = torch.arange(n2 * (d + 1)).view(d + 1, n2).t().reshape((n2 * (d + 1)))
                K = K[..., pi1, :][..., :, pi2]

            return K

        else:
            if not (n1 == n2 and torch.eq(x1, x2).all()):
                raise RuntimeError("diag=True only works when x1 == x2")

            kernel_diag = super(RBFKernelGrad, self).forward(x1, x2, diag=True)
            grad_diag = torch.ones(*batch_shape, n2, d, device=x1.device, dtype=x1.dtype) / self.lengthscale.pow(2)
            grad_diag = grad_diag.transpose(-1, -2).reshape(*batch_shape, n2 * d)
            k_diag = torch.cat((kernel_diag, grad_diag), dim=-1)
            if self._interleaved:
                pi = torch.arange(n2 * (d + 1)).view(d + 1, n2).t().reshape((n2 * (d + 1)))
                k_diag = k_diag[..., pi]
            return k_diag

    def num_outputs_per_input(self, x1, x2):
        return x1.size(-1) + 1
