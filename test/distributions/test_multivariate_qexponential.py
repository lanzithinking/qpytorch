#!/usr/bin/env python3

import math
import unittest
from itertools import product

import torch
from linear_operator import to_linear_operator
from linear_operator.operators import DenseLinearOperator, DiagLinearOperator, LinearOperator, RootLinearOperator
from torch.distributions import MultivariateNormal as TMultivariateNormal

from qpytorch.distributions import MultivariateQExponential
from qpytorch.test import BaseTestCase
from gpytorch.test.utils import least_used_cuda_device


class TestMultivariateQExponential(BaseTestCase, unittest.TestCase):
    seed = 1

    def test_multivariate_qexponential_non_lazy(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            power = torch.tensor(1., device=device, dtype=dtype)
            qep = MultivariateQExponential(mean=mean, covariance_matrix=covmat, power=power, validate_args=True)
            self.assertTrue(torch.is_tensor(qep.covariance_matrix))
            self.assertIsInstance(qep.lazy_covariance_matrix, LinearOperator)
            self.assertAllClose(qep.variance, torch.diag(covmat))
            self.assertAllClose(qep.scale_tril, covmat.sqrt())
            qep_plus1 = qep + 1
            self.assertAllClose(qep_plus1.mean, qep.mean + 1)
            self.assertAllClose(qep_plus1.covariance_matrix, qep.covariance_matrix)
            qep_times2 = qep * 2
            self.assertAllClose(qep_times2.mean, qep.mean * 2)
            self.assertAllClose(qep_times2.covariance_matrix, qep.covariance_matrix * 4)
            qep_divby2 = qep / 2
            self.assertAllClose(qep_divby2.mean, qep.mean / 2)
            self.assertAllClose(qep_divby2.covariance_matrix, qep.covariance_matrix / 4)
            self.assertAlmostEqual(qep.entropy().item(), 5.1988, places=4)
            self.assertAlmostEqual(qep.log_prob(torch.zeros(3, device=device, dtype=dtype)).item(), -5.5486, places=4)
            logprob = qep.log_prob(torch.zeros(2, 3, device=device, dtype=dtype))
            logprob_expected = torch.tensor([-5.5486, -5.5486], device=device, dtype=dtype)
            self.assertAllClose(logprob, logprob_expected)
            conf_lower, conf_upper = qep.confidence_region()
            self.assertAllClose(conf_lower, qep.mean - 2 * qep.stddev)
            self.assertAllClose(conf_upper, qep.mean + 2 * qep.stddev)
            self.assertTrue(qep.sample().shape == torch.Size([3]))
            self.assertTrue(qep.sample(torch.Size([2])).shape == torch.Size([2, 3]))
            self.assertTrue(qep.sample(torch.Size([2, 4])).shape == torch.Size([2, 4, 3]))

    def test_multivariate_qexponential_non_lazy_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_non_lazy(cuda=True)

    def test_multivariate_qexponential_batch_non_lazy(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            power = torch.tensor(1.0, device=device, dtype=dtype)
            qep = MultivariateQExponential(
                mean=mean.repeat(2, 1), covariance_matrix=covmat.repeat(2, 1, 1), power=power, validate_args=True
            )
            self.assertTrue(torch.is_tensor(qep.covariance_matrix))
            self.assertIsInstance(qep.lazy_covariance_matrix, LinearOperator)
            self.assertAllClose(qep.variance, covmat.diagonal(dim1=-1, dim2=-2).repeat(2, 1))
            self.assertAllClose(qep.scale_tril, torch.diag(covmat.diagonal(dim1=-1, dim2=-2).sqrt()).repeat(2, 1, 1))
            qep_plus1 = qep + 1
            self.assertAllClose(qep_plus1.mean, qep.mean + 1)
            self.assertAllClose(qep_plus1.covariance_matrix, qep.covariance_matrix)
            qep_times2 = qep * 2
            self.assertAllClose(qep_times2.mean, qep.mean * 2)
            self.assertAllClose(qep_times2.covariance_matrix, qep.covariance_matrix * 4)
            qep_divby2 = qep / 2
            self.assertAllClose(qep_divby2.mean, qep.mean / 2)
            self.assertAllClose(qep_divby2.covariance_matrix, qep.covariance_matrix / 4)
            self.assertAllClose(qep.entropy(), 5.1988 * torch.ones(2, device=device, dtype=dtype))
            logprob = qep.log_prob(torch.zeros(2, 3, device=device, dtype=dtype))
            logprob_expected = -5.5486 * torch.ones(2, device=device, dtype=dtype)
            self.assertAllClose(logprob, logprob_expected)
            logprob = qep.log_prob(torch.zeros(2, 2, 3, device=device, dtype=dtype))
            logprob_expected = -5.5486 * torch.ones(2, 2, device=device, dtype=dtype)
            self.assertAllClose(logprob, logprob_expected)
            conf_lower, conf_upper = qep.confidence_region()
            self.assertAllClose(conf_lower, qep.mean - 2 * qep.stddev)
            self.assertAllClose(conf_upper, qep.mean + 2 * qep.stddev)
            self.assertTrue(qep.sample().shape == torch.Size([2, 3]))
            self.assertTrue(qep.sample(torch.Size([2])).shape == torch.Size([2, 2, 3]))
            self.assertTrue(qep.sample(torch.Size([2, 4])).shape == torch.Size([2, 4, 2, 3]))

    def test_multivariate_qexponential_batch_non_lazy_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_batch_non_lazy(cuda=True)

    def test_multivariate_qexponential_lazy(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            covmat_chol = torch.linalg.cholesky(covmat)
            power = torch.tensor(1.0, device=device, dtype=dtype)
            qep = MultivariateQExponential(mean=mean, covariance_matrix=DenseLinearOperator(covmat), power=power)
            self.assertTrue(torch.is_tensor(qep.covariance_matrix))
            self.assertIsInstance(qep.lazy_covariance_matrix, LinearOperator)
            self.assertAllClose(qep.variance, torch.diag(covmat))
            self.assertAllClose(qep.covariance_matrix, covmat)
            self.assertAllClose(qep._unbroadcasted_scale_tril, covmat_chol)
            qep_plus1 = qep + 1
            self.assertAllClose(qep_plus1.mean, qep.mean + 1)
            self.assertAllClose(qep_plus1.covariance_matrix, qep.covariance_matrix)
            self.assertAllClose(qep_plus1._unbroadcasted_scale_tril, covmat_chol)
            qep_times2 = qep * 2
            self.assertAllClose(qep_times2.mean, qep.mean * 2)
            self.assertAllClose(qep_times2.covariance_matrix, qep.covariance_matrix * 4)
            self.assertAllClose(qep_times2._unbroadcasted_scale_tril, covmat_chol * 2)
            qep_divby2 = qep / 2
            self.assertAllClose(qep_divby2.mean, qep.mean / 2)
            self.assertAllClose(qep_divby2.covariance_matrix, qep.covariance_matrix / 4)
            self.assertAllClose(qep_divby2._unbroadcasted_scale_tril, covmat_chol / 2)
            # TODO: Add tests for entropy, log_prob, etc. - this an issue b/c it
            # uses using root_decomposition which is not very reliable
            # self.assertAlmostEqual(qep.entropy().item(), 4.3157, places=4)
            # self.assertAlmostEqual(qep.log_prob(torch.zeros(3)).item(), -4.8157, places=4)
            # self.assertTrue(
            #     torch.allclose(
            #         qep.log_prob(torch.zeros(2, 3)), -4.8157 * torch.ones(2))
            #     )
            # )
            conf_lower, conf_upper = qep.confidence_region()
            self.assertAllClose(conf_lower, qep.mean - 2 * qep.stddev)
            self.assertAllClose(conf_upper, qep.mean + 2 * qep.stddev)
            self.assertTrue(qep.sample().shape == torch.Size([3]))
            self.assertTrue(qep.sample(torch.Size([2])).shape == torch.Size([2, 3]))
            self.assertTrue(qep.sample(torch.Size([2, 4])).shape == torch.Size([2, 4, 3]))

    def test_multivariate_qexponential_lazy_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_lazy(cuda=True)

    def test_multivariate_qexponential_batch_lazy(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype).repeat(2, 1)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype)).repeat(2, 1, 1)
            covmat_chol = torch.linalg.cholesky(covmat)
            power = torch.tensor(1.0, device=device, dtype=dtype)
            qep = MultivariateQExponential(mean=mean, covariance_matrix=DenseLinearOperator(covmat), power=power)
            self.assertTrue(torch.is_tensor(qep.covariance_matrix))
            self.assertIsInstance(qep.lazy_covariance_matrix, LinearOperator)
            self.assertAllClose(qep.variance, torch.diagonal(covmat, dim1=-2, dim2=-1))
            self.assertAllClose(qep._unbroadcasted_scale_tril, covmat_chol)
            qep_plus1 = qep + 1
            self.assertAllClose(qep_plus1.mean, qep.mean + 1)
            self.assertAllClose(qep_plus1.covariance_matrix, qep.covariance_matrix)
            self.assertAllClose(qep_plus1._unbroadcasted_scale_tril, covmat_chol)
            qep_times2 = qep * 2
            self.assertAllClose(qep_times2.mean, qep.mean * 2)
            self.assertAllClose(qep_times2.covariance_matrix, qep.covariance_matrix * 4)
            self.assertAllClose(qep_times2._unbroadcasted_scale_tril, covmat_chol * 2)
            qep_divby2 = qep / 2
            self.assertAllClose(qep_divby2.mean, qep.mean / 2)
            self.assertAllClose(qep_divby2.covariance_matrix, qep.covariance_matrix / 4)
            self.assertAllClose(qep_divby2._unbroadcasted_scale_tril, covmat_chol / 2)
            # TODO: Add tests for entropy, log_prob, etc. - this an issue b/c it
            # uses using root_decomposition which is not very reliable
            # self.assertTrue(torch.allclose(qep.entropy(), 4.3157 * torch.ones(2)))
            # self.assertTrue(
            #     torch.allclose(qep.log_prob(torch.zeros(2, 3)), -4.8157 * torch.ones(2))
            # )
            # self.assertTrue(
            #     torch.allclose(qep.log_prob(torch.zeros(2, 2, 3)), -4.8157 * torch.ones(2, 2))
            # )
            conf_lower, conf_upper = qep.confidence_region()
            self.assertAllClose(conf_lower, qep.mean - 2 * qep.stddev)
            self.assertAllClose(conf_upper, qep.mean + 2 * qep.stddev)
            self.assertTrue(qep.sample().shape == torch.Size([2, 3]))
            self.assertTrue(qep.sample(torch.Size([2])).shape == torch.Size([2, 2, 3]))
            self.assertTrue(qep.sample(torch.Size([2, 4])).shape == torch.Size([2, 4, 2, 3]))

    def test_multivariate_qexponential_batch_lazy_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_batch_lazy(cuda=True)

    def test_multivariate_qexponential_correlated_samples(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            power = torch.tensor(1.0, device=device, dtype=dtype)
            qep = MultivariateQExponential(mean=mean, covariance_matrix=DenseLinearOperator(covmat), power=power)
            base_samples = qep.get_base_samples(torch.Size([3, 4]))
            self.assertTrue(qep.sample(base_samples=base_samples).shape == torch.Size([3, 4, 3]))
            base_samples = qep.get_base_samples()
            self.assertTrue(qep.sample(base_samples=base_samples).shape == torch.Size([3]))

    def test_multivariate_qexponential_correlated_samples_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_correlated_samples(cuda=True)

    def test_multivariate_qexponential_batch_correlated_samples(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            power = torch.tensor(1.0, device=device, dtype=dtype)
            qep = MultivariateQExponential(
                mean=mean.repeat(2, 1), covariance_matrix=DenseLinearOperator(covmat).repeat(2, 1, 1), power=power
            )
            base_samples = qep.get_base_samples(torch.Size((3, 4)))
            self.assertTrue(qep.sample(base_samples=base_samples).shape == torch.Size([3, 4, 2, 3]))
            base_samples = qep.get_base_samples()
            self.assertTrue(qep.sample(base_samples=base_samples).shape == torch.Size([2, 3]))

    def test_multivariate_qexponential_batch_correlated_samples_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_multivariate_qexponential_batch_correlated_samples(cuda=True)

    def test_log_prob(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean = torch.randn(4, device=device, dtype=dtype)
            var = torch.randn(4, device=device, dtype=dtype).abs_()
            values = torch.randn(4, device=device, dtype=dtype)

            res = MultivariateQExponential(mean, DiagLinearOperator(var)).log_prob(values)
            actual = TMultivariateNormal(mean, torch.eye(4, device=device, dtype=dtype) * var).log_prob(values)
            self.assertLess((res - actual).div(res).abs().item(), 1e-2)

            mean = torch.randn(3, 4, device=device, dtype=dtype)
            var = torch.randn(3, 4, device=device, dtype=dtype).abs_()
            values = torch.randn(3, 4, device=device, dtype=dtype)

            res = MultivariateQExponential(mean, DiagLinearOperator(var)).log_prob(values)
            actual = TMultivariateNormal(
                mean, var.unsqueeze(-1) * torch.eye(4, device=device, dtype=dtype).repeat(3, 1, 1)
            ).log_prob(values)
            self.assertLess((res - actual).div(res).abs().norm(), 1e-2)

    def test_log_prob_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_log_prob(cuda=True)

    def test_kl_divergence(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype in (torch.float, torch.double):
            mean0 = torch.randn(4, device=device, dtype=dtype)
            mean1 = mean0 + 1
            var0 = torch.randn(4, device=device, dtype=dtype).abs_()
            var1 = var0 * math.exp(2)
            power = torch.tensor(1.0, device=device, dtype=dtype)

            dist_a = MultivariateQExponential(mean0, DiagLinearOperator(var0), power)
            dist_b = MultivariateQExponential(mean1, DiagLinearOperator(var0), power)
            dist_c = MultivariateQExponential(mean0, DiagLinearOperator(var1), power)

            res = torch.distributions.kl.kl_divergence(dist_a, dist_a)
            actual = 0.0
            self.assertLess((res - actual).abs().item(), 1e-2)

            dist_a.power = torch.tensor(2.0, device=device, dtype=dtype)
            dist_b.power = torch.tensor(2.0, device=device, dtype=dtype)
            dist_c.power = torch.tensor(2.0, device=device, dtype=dtype)
            
            res = torch.distributions.kl.kl_divergence(dist_b, dist_a)
            actual = var0.reciprocal().sum().div(2.0)
            self.assertLess((res - actual).div(res).abs().item(), 1e-2)

            res = torch.distributions.kl.kl_divergence(dist_a, dist_c)
            actual = 0.5 * (8 - 4 + 4 * math.exp(-2))
            self.assertLess((res - actual).div(res).abs().item(), 1e-2)

    def test_kl_divergence_cuda(self):
        if torch.cuda.is_available():
            with least_used_cuda_device():
                self.test_kl_divergence(cuda=True)

    def test_getitem(self):
        shape = (2, 4, 3, 2)
        cov = torch.randn(*shape, shape[1])
        cov = cov @ cov.transpose(-1, -2)
        mean = torch.randn(*shape)
        power = torch.tensor(1.0)
        dist = MultivariateQExponential(mean, cov, power)
        dist_cov = dist.covariance_matrix

        d = dist[1]
        assert torch.equal(d.mean, dist.mean[1])
        self.assertAllClose(d.covariance_matrix, dist_cov[1])

        d = dist[..., 1]
        assert torch.equal(d.mean, dist.mean[..., 1])
        cov = dist_cov[..., 1, 1]
        self.assertAllClose(d.covariance_matrix, cov.unsqueeze(-1) * torch.eye(shape[-2]))

        d = dist[:, [2, 3], :, 1:]
        assert torch.equal(d.mean, dist.mean[:, [2, 3], :, 1:])
        self.assertAllClose(d.covariance_matrix, dist_cov[:, [2, 3], :, 1:, 1:])

        d = dist[:, :, ..., [0, 1, 1, 0]]
        assert torch.equal(d.mean, dist.mean[..., [0, 1, 1, 0]])
        self.assertAllClose(d.covariance_matrix, dist_cov[..., [0, 1, 1, 0], :][..., [0, 1, 1, 0]])

        d = dist[1, 2, 2, ...]
        assert torch.equal(d.mean, dist.mean[1, 2, 2, :])
        self.assertAllClose(d.covariance_matrix, dist_cov[1, 2, 2, :, :])

        d = dist[0, 1, ..., 2, 1]
        assert torch.equal(d.mean, dist.mean[0, 1, 2, 1])
        self.assertAllClose(d.covariance_matrix, dist_cov[0, 1, 2, 1, 1])

    def test_base_sample_shape(self):
        a = torch.randn(5, 10)
        lazy_square_a = RootLinearOperator(to_linear_operator(a))
        power = torch.tensor(1.0)
        dist = MultivariateQExponential(torch.zeros(5), lazy_square_a, power)

        # check that providing the base samples is okay
        samples = dist.rsample(torch.Size((16,)), base_samples=torch.randn(16, 10))
        self.assertEqual(samples.shape, torch.Size((16, 5)))

        # check that an event shape of base samples fails
        self.assertRaises(RuntimeError, dist.rsample, torch.Size((16,)), base_samples=torch.randn(16, 5))

        # check that the proper event shape of base samples is okay for
        # a non root lt
        nonlazy_square_a = to_linear_operator(lazy_square_a.to_dense())
        dist = MultivariateQExponential(torch.zeros(5), nonlazy_square_a, power)

        samples = dist.rsample(torch.Size((16,)), base_samples=torch.randn(16, 5))
        self.assertEqual(samples.shape, torch.Size((16, 5)))

    def test_multivariate_qexponential_expand(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype, lazy in product((torch.float, torch.double), (True, False)):
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype))
            power = torch.tensor(1.0, device=device, dtype=dtype)
            if lazy:
                qep = MultivariateQExponential(mean=mean, covariance_matrix=DenseLinearOperator(covmat), validate_args=True, power=power)
                # Initialize scale tril so we can test that it was expanded.
                qep.scale_tril
            else:
                qep = MultivariateQExponential(mean=mean, covariance_matrix=covmat, validate_args=True, power=power)
            self.assertEqual(qep.batch_shape, torch.Size([]))
            self.assertEqual(qep.islazy, lazy)
            expanded = qep.expand(torch.Size([2]))
            self.assertIsInstance(expanded, MultivariateQExponential)
            self.assertEqual(expanded.islazy, lazy)
            self.assertEqual(expanded.batch_shape, torch.Size([2]))
            self.assertEqual(expanded.event_shape, qep.event_shape)
            self.assertTrue(torch.equal(expanded.mean, mean.expand(2, -1)))
            self.assertEqual(expanded.mean.shape, torch.Size([2, 3]))
            self.assertTrue(torch.allclose(expanded.covariance_matrix, covmat.expand(2, -1, -1)))
            self.assertEqual(expanded.covariance_matrix.shape, torch.Size([2, 3, 3]))
            self.assertTrue(torch.allclose(expanded.scale_tril, qep.scale_tril.expand(2, -1, -1)))
            self.assertEqual(expanded.scale_tril.shape, torch.Size([2, 3, 3]))

    def test_multivariate_normal_unsqueeze(self, cuda=False):
        device = torch.device("cuda") if cuda else torch.device("cpu")
        for dtype, lazy in product((torch.float, torch.double), (True, False)):
            batch_shape = torch.Size([2, 3])
            mean = torch.tensor([0, 1, 2], device=device, dtype=dtype).expand(*batch_shape, -1)
            covmat = torch.diag(torch.tensor([1, 0.75, 1.5], device=device, dtype=dtype)).expand(*batch_shape, -1, -1)
            power = torch.tensor(1.0, device=device, dtype=dtype)
            if lazy:
                qep = MultivariateQExponential(mean=mean, covariance_matrix=DenseLinearOperator(covmat), validate_args=True, power=power)
                # Initialize scale tril so we can test that it was unsqueezed.
                qep.scale_tril
            else:
                qep = MultivariateQExponential(mean=mean, covariance_matrix=covmat, validate_args=True, power=power)
            self.assertEqual(qep.batch_shape, batch_shape)
            self.assertEqual(qep.islazy, lazy)
            for dim, positive_dim, expected_batch in ((1, 1, torch.Size([2, 1, 3])), (-1, 2, torch.Size([2, 3, 1]))):
                new = qep.unsqueeze(dim)
                self.assertIsInstance(new, MultivariateQExponential)
                self.assertEqual(new.islazy, lazy)
                self.assertEqual(new.batch_shape, expected_batch)
                self.assertEqual(new.event_shape, qep.event_shape)
                self.assertTrue(torch.equal(new.mean, mean.unsqueeze(positive_dim)))
                self.assertEqual(new.mean.shape, expected_batch + torch.Size([3]))
                self.assertTrue(torch.allclose(new.covariance_matrix, covmat.unsqueeze(positive_dim)))
                self.assertEqual(new.covariance_matrix.shape, expected_batch + torch.Size([3, 3]))
                self.assertTrue(torch.allclose(new.scale_tril, qep.scale_tril.unsqueeze(positive_dim)))
                self.assertEqual(new.scale_tril.shape, expected_batch + torch.Size([3, 3]))

        # Check for dim validation.
        with self.assertRaisesRegex(IndexError, "Dimension out of range"):
            qep.unsqueeze(3)
        with self.assertRaisesRegex(IndexError, "Dimension out of range"):
            qep.unsqueeze(-4)
        # Should not raise error up to 2 or -3.
        qep.unsqueeze(2)
        qep.unsqueeze(-3)

if __name__ == "__main__":
    unittest.main()
