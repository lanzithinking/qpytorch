#!/usr/bin/env python3

import os
import random
import unittest
from math import exp, pi

import torch
from torch import optim

import qpytorch
from qpytorch.distributions import MultivariateQExponential
from qpytorch.kernels import IndexKernel, RBFKernel
from qpytorch.likelihoods import QExponentialLikelihood
from qpytorch.means import ConstantMean
from qpytorch.priors import LKJCovariancePrior, SmoothedBoxPrior

# Simple training data: let's try to learn a sine function
train_x = torch.linspace(0, 1, 100)
y1_inds = torch.zeros(100, dtype=torch.long)
y2_inds = torch.ones(100, dtype=torch.long)
train_y1 = torch.sin(train_x * (2 * pi)) + torch.randn_like(train_x).mul_(1e-2)
train_y2 = torch.cos(train_x * (2 * pi)) + torch.randn_like(train_x).mul_(1e-2)

test_x = torch.linspace(0, 1, 51)
y1_inds_test = torch.zeros(51, dtype=torch.long)
y2_inds_test = torch.ones(51, dtype=torch.long)
test_y1 = torch.sin(test_x * (2 * pi))
test_y2 = torch.cos(test_x * (2 * pi))

POWER = 1.0

class HadamardMultitaskQEPModel(qpytorch.models.ExactQEP):
    def __init__(self, train_x, train_y, likelihood):
        super(HadamardMultitaskQEPModel, self).__init__(train_x, train_y, likelihood)
        # Default bounds on mean are (-1e10, 1e10)
        self.mean_module = ConstantMean()
        # We use the very common RBF kernel
        self.covar_module = RBFKernel()
        # We learn an IndexKernel for 2 tasks
        # (so we'll actually learn 2x2=4 tasks with correlations)
        sd_prior = SmoothedBoxPrior(exp(-4), exp(4))
        cov_prior = LKJCovariancePrior(n=2, eta=1, sd_prior=sd_prior)
        self.task_covar_module = IndexKernel(num_tasks=2, rank=1, prior=cov_prior)

    def forward(self, x, i):
        # Get predictive mean
        mean_x = self.mean_module(x)
        # Get all covariances, we'll look up the task-speicific ones
        covar_x = self.covar_module(x)
        # # Get the covariance for task i
        covar_i = self.task_covar_module(i)
        covar_xi = covar_x.mul(covar_i)
        return MultivariateQExponential(mean_x, covar_xi, power=self.likelihood.power)


class TestHadamardMultitaskQEPRegression(unittest.TestCase):
    def setUp(self):
        if os.getenv("UNLOCK_SEED") is None or os.getenv("UNLOCK_SEED").lower() == "false":
            self.rng_state = torch.get_rng_state()
            torch.manual_seed(0)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(0)
            random.seed(0)

    def tearDown(self):
        if hasattr(self, "rng_state"):
            torch.set_rng_state(self.rng_state)

    def test_multitask_qep_mean_abs_error(self):
        likelihood = QExponentialLikelihood(noise_prior=SmoothedBoxPrior(-6, 6), power=torch.tensor(POWER))
        qep_model = HadamardMultitaskQEPModel(
            (torch.cat([train_x, train_x]), torch.cat([y1_inds, y2_inds])), torch.cat([train_y1, train_y2]), likelihood
        )
        mll = qpytorch.mlls.ExactMarginalLogLikelihood(likelihood, qep_model)

        # Optimize the model
        qep_model.train()
        likelihood.eval()
        optimizer = optim.Adam(qep_model.parameters(), lr=0.01)
        for _ in range(100):
            optimizer.zero_grad()
            output = qep_model(torch.cat([train_x, train_x]), torch.cat([y1_inds, y2_inds]))
            loss = -mll(output, torch.cat([train_y1, train_y2]))
            loss.backward()
            optimizer.step()

            for param in qep_model.parameters():
                self.assertTrue(param.grad is not None)
                self.assertGreater(param.grad.norm().item(), 0)

        # Test the model
        qep_model.eval()
        likelihood.eval()
        test_preds_task_1 = likelihood(qep_model(test_x, y1_inds_test)).mean
        mean_abs_error_task_1 = torch.mean(torch.abs(test_y1 - test_preds_task_1))

        self.assertLess(mean_abs_error_task_1.item(), 0.1)

        test_preds_task_2 = likelihood(qep_model(test_x, y2_inds_test)).mean
        mean_abs_error_task_2 = torch.mean(torch.abs(test_y2 - test_preds_task_2))

        self.assertLess(mean_abs_error_task_2.item(), 0.1)


if __name__ == "__main__":
    unittest.main()
