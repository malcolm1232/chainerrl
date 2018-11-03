from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from builtins import *  # NOQA
from future import standard_library
standard_library.install_aliases()  # NOQA

import chainer
from chainer import cuda
from chainer import functions as F
from chainer import links as L
import numpy as np

from chainerrl import action_value
from chainerrl.links.mlp import MLP
from chainerrl.q_function import StateQFunction
from chainerrl.recurrent import RecurrentChainMixin


class DuelingDQN(chainer.Chain, StateQFunction):
    """Dueling Q-Network

    See: http://arxiv.org/abs/1511.06581
    """

    def __init__(self, n_actions, n_input_channels=4,
                 activation=F.relu, bias=0.1):
        self.n_actions = n_actions
        self.n_input_channels = n_input_channels
        self.activation = activation

        super().__init__()
        with self.init_scope():
            self.conv_layers = chainer.ChainList(
                L.Convolution2D(n_input_channels, 32, 8, stride=4,
                                initial_bias=bias),
                L.Convolution2D(32, 64, 4, stride=2, initial_bias=bias),
                L.Convolution2D(64, 64, 3, stride=1, initial_bias=bias))

            self.a_stream = MLP(3136, n_actions, [512])
            self.v_stream = MLP(3136, 1, [512])

    def __call__(self, x):
        h = x
        for l in self.conv_layers:
            h = self.activation(l(h))

        # Advantage
        batch_size = x.shape[0]
        ya = self.a_stream(h)
        mean = F.reshape(
            F.sum(ya, axis=1) / self.n_actions, (batch_size, 1))
        ya, mean = F.broadcast(ya, mean)
        ya -= mean

        # State value
        ys = self.v_stream(h)

        ya, ys = F.broadcast(ya, ys)
        q = ya + ys
        return action_value.DiscreteActionValue(q)


class DistributionalDuelingDQN(
        chainer.Chain, StateQFunction, RecurrentChainMixin):
    """Distributional dueling fully-connected Q-function with discrete actions.

    Args:
        n_dim_obs (int): Number of dimensions of observation space.
        n_actions (int): Number of actions in action space.
        n_atoms (int): Number of atoms of return distribution.
        v_min (float): Minimum value this model can approximate.
        v_max (float): Maximum value this model can approximate.
        n_hidden_channels (int): Number of hidden channels.
        n_hidden_layers (int): Number of hidden layers.
        nonlinearity (callable): Nonlinearity applied after each hidden layer.
        last_wscale (float): Weight scale of the last layer.
    """

    def __init__(self, n_actions, n_atoms, v_min, v_max,
                 n_input_channels=4, activation=F.relu, bias=0.1):
        assert n_atoms >= 2
        assert v_min < v_max

        self.n_actions = n_actions
        self.n_input_channels = n_input_channels
        self.activation = activation
        self.n_atoms = n_atoms

        self.z_values = np.linspace(v_min, v_max, num=n_atoms, dtype=np.float32)
        self.add_persistent('z_values', self.z_values)

        super().__init__()
        with self.init_scope():
            self.conv_layers = chainer.ChainList(
                L.Convolution2D(n_input_channels, 32, 8, stride=4,
                                initial_bias=bias),
                L.Convolution2D(32, 64, 4, stride=2, initial_bias=bias),
                L.Convolution2D(64, 64, 3, stride=1, initial_bias=bias))

            self.a_stream = MLP(3136, n_actions * n_atoms, [512])
            self.v_stream = MLP(3136, n_atoms, [512])

    def __call__(self, x):
        h = x
        for l in self.conv_layers:
            h = self.activation(l(h))

        # Advantage
        batch_size = x.shape[0]
        ya = self.a_stream(h)
        ya = F.reshape(ya, (batch_size, self.n_actions, self.n_atoms))
        mean = F.reshape(
            F.sum(ya, axis=1) / self.n_actions, (batch_size, 1, self.n_atoms))
        ya, mean = F.broadcast(ya, mean)
        ya -= mean

        # State value
        ys = self.v_stream(h)
        ys = F.reshape(ys, (batch_size, 1, self.n_atoms))

        ya, ys = F.broadcast(ya, ys)
        q = ya + ys

        return action_value.DistributionalDiscreteActionValue(q, self.z_values)
