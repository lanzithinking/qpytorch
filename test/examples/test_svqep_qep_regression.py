#!/usr/bin/env python3

import math
import unittest
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import linear_operator
import torch
from torch import optim

import qpytorch
from qpytorch.likelihoods import QExponentialLikelihood
from qpytorch.models import ApproximateQEP
from qpytorch.test import BaseTestCase
from gpytorch.test.utils import least_used_cuda_device
from qpytorch.utils.warnings import OldVersionWarning

POWER = 1.99

def train_data(cuda=False):
    train_x = torch.linspace(0, 1, 260)
    train_y = torch.cos(train_x * (2 * math.pi))
    if cuda:
        return train_x.cuda(), train_y.cuda()
    else:
        return train_x, train_y


class SVQEPRegressionModel(ApproximateQEP):
    def __init__(self, inducing_points, distribution_cls):
        self.power = torch.tensor(POWER)
        variational_distribution = distribution_cls(inducing_points.size(-1), power=self.power)
        variational_strategy = qpytorch.variational.VariationalStrategy(
            self, inducing_points, variational_distribution, learn_inducing_locations=True, jitter_val=1e-4
        )
        super(SVQEPRegressionModel, self).__init__(variational_strategy)
        self.mean_module = qpytorch.means.ConstantMean()
        self.covar_module = qpytorch.kernels.ScaleKernel(qpytorch.kernels.RBFKernel())

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        latent_pred = qpytorch.distributions.MultivariateQExponential(mean_x, covar_x, power=self.power)
        return latent_pred


class TestSVQEPRegression(BaseTestCase, unittest.TestCase):
    seed = 0

    def test_loading_old_model(self):
        train_x, train_y = train_data(cuda=False)
        likelihood = QExponentialLikelihood(power=torch.tensor(POWER))
        model = SVQEPRegressionModel(torch.linspace(0, 1, 25), qpytorch.variational.CholeskyVariationalDistribution)
        data_file = Path(__file__).parent.joinpath("old_variational_strategy_model.pth").resolve()
        state_dicts = torch.load(data_file)
        likelihood.load_state_dict(state_dicts["likelihood"], strict=False)

        # Ensure we get a warning
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always", OldVersionWarning)

            model.load_state_dict(state_dicts["model"])
            self.assertTrue(any(issubclass(w.category, OldVersionWarning) for w in ws))

        with torch.no_grad():
            model.eval()
            likelihood.eval()
            test_preds = likelihood(model(train_x)).mean.squeeze()
            mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)
            self.assertLess(mean_abs_error.item(), 1e-1)

    def test_regression_error(
        self,
        cuda=False,
        mll_cls=qpytorch.mlls.VariationalELBO,
        distribution_cls=qpytorch.variational.CholeskyVariationalDistribution,
    ):
        train_x, train_y = train_data(cuda=cuda)
        likelihood = QExponentialLikelihood(power=torch.tensor(POWER))
        model = SVQEPRegressionModel(torch.linspace(0, 1, 25), distribution_cls)
        mll = mll_cls(likelihood, model, num_data=len(train_y))
        if cuda:
            likelihood = likelihood.cuda()
            model = model.cuda()
            mll = mll.cuda()

        # Find optimal model hyperparameters
        model.train()
        likelihood.train()
        optimizer = optim.Adam([{"params": model.parameters()}, {"params": likelihood.parameters()}], lr=0.01)

        _wrapped_cg = MagicMock(wraps=linear_operator.utils.linear_cg)
        _cg_mock = patch("linear_operator.utils.linear_cg", new=_wrapped_cg)
        with _cg_mock as cg_mock:
            for _ in range(250):
                optimizer.zero_grad()
                output = model(train_x)
                loss = -mll(output, train_y)
                loss.backward()
                optimizer.step()

            for param in model.parameters():
                self.assertTrue(param.grad is not None)
                self.assertGreater(param.grad.norm().item(), 0)
            for param in likelihood.parameters():
                self.assertTrue(param.grad is not None)
                self.assertGreater(param.grad.norm().item(), 0)

            # Set back to eval mode
            model.eval()
            likelihood.eval()
            test_preds = likelihood(model(train_x)).mean.squeeze()
            mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)
            self.assertLess(mean_abs_error.item(), 0.20)

            # Make sure CG was called (or not), and no warnings were thrown
            self.assertFalse(cg_mock.called)

            if distribution_cls is qpytorch.variational.CholeskyVariationalDistribution:
                # finally test fantasization
                # we only will check that tossing the entire training set into the model will reduce the mae
                model.likelihood = likelihood
                fant_model = model.get_fantasy_model(train_x, train_y)
                fant_preds = fant_model.likelihood(fant_model(train_x)).mean.squeeze()
                updated_abs_error = torch.mean(torch.abs(train_y - fant_preds) / 2)
                # TODO: figure out why this error is worse than before
                self.assertLess(updated_abs_error.item(), 0.15)

    def test_predictive_ll_regression_error(self):
        return self.test_regression_error(
            mll_cls=qpytorch.mlls.PredictiveLogLikelihood,
            distribution_cls=qpytorch.variational.MeanFieldVariationalDistribution,
        )

    def test_predictive_ll_regression_error_delta(self):
        return self.test_regression_error(
            mll_cls=qpytorch.mlls.PredictiveLogLikelihood,
            distribution_cls=qpytorch.variational.DeltaVariationalDistribution,
        )

    def test_robust_regression_error(self):
        return self.test_regression_error(mll_cls=qpytorch.mlls.GammaRobustVariationalELBO)

    def test_regression_error_cuda(self):
        if not torch.cuda.is_available():
            return
        with least_used_cuda_device():
            return self.test_regression_error(cuda=True)


if __name__ == "__main__":
    unittest.main()
