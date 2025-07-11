#!/usr/bin/env python3

import unittest

import torch
from linear_operator.operators import DiagLinearOperator

from qpytorch.distributions import MultivariateNormal, MultivariateQExponential
from gpytorch.likelihoods import GaussianLikelihood
from qpytorch.likelihoods import QExponentialLikelihood
from qpytorch.test import BaseTestCase

TEST_MDL = 'QEP'
mlls = {'GP': 'gpytorch.mlls', 'QEP': 'qpytorch.mlls'}[TEST_MDL]
exec(f"from {mlls} import {'InducingPointKernelAddedLossTerm'} ")

POWER = 2.0

class TestInducingPointKernelAddedLossTerm(BaseTestCase, unittest.TestCase):
    def test_added_loss_term(self):
        # This loss term won't usually be called with diagonal MVNs
        # However, the loss term only accesses the diagonals of the MVN covariance matrices
        # So we're simplifying the setup for the unit test
        if TEST_MDL == 'GP':
            prior_dist = MultivariateNormal(torch.zeros(5), DiagLinearOperator(torch.tensor([1.0, 1.0, 1.0, 1.0, 1.0])))
            variational_dist = MultivariateNormal(
                torch.zeros(5), DiagLinearOperator(torch.tensor([0.6, 0.7, 0.8, 0.9, 1.0]))
            )
            likelihood = GaussianLikelihood()
        elif TEST_MDL == 'QEP':
            power = torch.tensor(POWER)
            prior_dist = MultivariateQExponential(torch.zeros(5), DiagLinearOperator(torch.tensor([1.0, 1.0, 1.0, 1.0, 1.0])), power)
            variational_dist = MultivariateQExponential(
                torch.zeros(5), DiagLinearOperator(torch.tensor([0.6, 0.7, 0.8, 0.9, 1.0])), power,
            )
            likelihood = QExponentialLikelihood(power=power)
        likelihood.noise = 0.01

        added_loss_term = InducingPointKernelAddedLossTerm(prior_dist, variational_dist, likelihood)
        self.assertAllClose(added_loss_term.loss(), torch.tensor(-50.0))

    def test_added_loss_term_batch(self):
        if TEST_MDL == 'GP':
            prior_dist = MultivariateNormal(
                torch.zeros(2, 5), DiagLinearOperator(torch.tensor([[1.0, 1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0, 1.0]]))
            )
            variational_dist = MultivariateNormal(
                torch.zeros(2, 5),
                DiagLinearOperator(torch.tensor([[0.6, 0.7, 0.8, 0.9, 1.0], [0.8, 0.85, 0.9, 0.95, 1.0]])),
            )
            likelihood = GaussianLikelihood(batch_shape=torch.Size([3, 1]))
        elif TEST_MDL == 'QEP':
            power = torch.tensor(POWER)
            prior_dist = MultivariateQExponential(
                torch.zeros(2, 5), DiagLinearOperator(torch.tensor([[1.0, 1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0, 1.0]])), power,
            )
            variational_dist = MultivariateQExponential(
                torch.zeros(2, 5),
                DiagLinearOperator(torch.tensor([[0.6, 0.7, 0.8, 0.9, 1.0], [0.8, 0.85, 0.9, 0.95, 1.0]])),
                power,
            )
            likelihood = QExponentialLikelihood(batch_shape=torch.Size([3, 1]), power=power)
        likelihood.noise = torch.Tensor([[0.01], [0.1], [1.0]])

        added_loss_term = InducingPointKernelAddedLossTerm(prior_dist, variational_dist, likelihood)
        self.assertAllClose(added_loss_term.loss(), torch.tensor([[-50.0, -25.0], [-5.0, -2.5], [-0.5, -0.25]]))


if __name__ == "__main__":
    unittest.main()
