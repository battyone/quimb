"""Generate specific tensor network states and operators.
"""
import numpy as np

from ..accel import make_immutable
from ..linalg.base_linalg import norm_fro_dense
from ..gen.operators import spin_operator, eye
from .tensor_core import Tensor
from .tensor_1d import MatrixProductState, MatrixProductOperator


def rand_tensor(shape, inds, tags=None):
    """Generate a random (complex) tensor with specified shape and inds.
    """
    data = np.random.randn(*shape) + 1.0j * np.random.randn(*shape)
    return Tensor(data=data, inds=inds, tags=tags)


# --------------------------------------------------------------------------- #
#                                    MPSs                                     #
# --------------------------------------------------------------------------- #

def MPS_rand_state(n, bond_dim, phys_dim=2,
                   site_ind_id='k{}',
                   site_tag_id='i{}',
                   tags=None,
                   bond_name="",
                   normalize=True,
                   **mps_opts):
    """Generate a random matrix product state.

    Parameters
    ----------
    bond_dim : int
        The bond dimension.
    phys_dim : int, optional
        The physical (site) dimensions, defaults to 2.
    site_ind_id : sequence of hashable, or str
        See :class:`~quimb.tensor.tensor_1d.MatrixProductState`.
    site_tag_id=None, optional
        See :class:`~quimb.tensor.tensor_1d.MatrixProductState`.
    tags=None, optional
        See :class:`~quimb.tensor.tensor_1d.MatrixProductState`.
    bond_name : str, optional
        See :class:`~quimb.tensor.tensor_1d.MatrixProductState`.
    """
    shapes = [(bond_dim, phys_dim),
              *((bond_dim, bond_dim, phys_dim),) * (n - 2),
              (bond_dim, phys_dim)]

    arrays = \
        map(lambda x: x / norm_fro_dense(x)**(1 / (x.ndim - 1)),
            map(lambda x: np.random.randn(*x) + 1.0j * np.random.randn(*x),
                shapes))

    rmps = MatrixProductState(arrays, site_ind_id=site_ind_id,
                              bond_name=bond_name, site_tag_id=site_tag_id,
                              tags=tags, **mps_opts)

    if normalize:
        rmps.site[-1] /= (rmps.H @ rmps)**0.5

    return rmps


def MPS_product_state(arrays, **mps_opts):
    """Generate a product state in MatrixProductState form, i,e,
    with bond dimension 1, from single site vectors described by ``arrays``.
    """
    def gen_array_shapes():
        yield (1, -1)
        for _ in range(len(arrays) - 2):
            yield (1, 1, -1)
        yield (1, -1)

    mps_arrays = (np.asarray(array).reshape(*shape)
                  for array, shape in zip(arrays, gen_array_shapes()))

    return MatrixProductState(mps_arrays, shape='lrp', **mps_opts)


def MPS_computational_state(binary_str, **mps_opts):
    """A computational basis state in Matrix Product State form.

    Parameters
    ----------
    binary_str : str
        String specifying the state, e.g. '00101010111'
    mps_opts
        Supplied to MatrixProductState constructor.
    """
    array_map = {
        '0': np.array([1., 0.]),
        '1': np.array([0., 1.]),
    }

    def gen_arrays():
        for s in binary_str:
            yield array_map[s]

    return MPS_product_state(tuple(gen_arrays()), **mps_opts)


def MPS_neel_state(n, down_first=False, **mps_opts):
    """Generate the neel state in Matrix Product State form.

    Parameters
    ----------
    n : int
        The number of spins.
    down_first : bool, optional
        Whether to start with '1' or '0' first.
    mps_opts
        Supplied to MatrixProductState constructor.
    """
    binary_str = "01" * (n // 2) + (n % 2 == 1) * "0"
    if down_first:
        binary_str = "1" + binary_str[:-1]
    return MPS_computational_state(binary_str, **mps_opts)


def MPS_zero_state(n, bond_dim=1, phys_dim=2, **mps_opts):
    """The all-zeros MPS state, of given bond-dimension.
    """
    def gen_arrays():
        yield np.zeros((bond_dim, phys_dim))
        for _ in range(n - 2):
            yield np.zeros((bond_dim, bond_dim, phys_dim))
        yield np.zeros((bond_dim, phys_dim))

    return MatrixProductState(gen_arrays(), **mps_opts)


# --------------------------------------------------------------------------- #
#                                    MPOs                                     #
# --------------------------------------------------------------------------- #

def MPO_identity(n, phys_dim=2, **mpo_opts):
    """Generate an identity MPO of size ``n``.
    """
    def gen_arrays():
        yield np.identity(phys_dim).reshape(1, phys_dim, phys_dim)
        for _ in range(n - 2):
            yield np.identity(phys_dim).reshape(1, 1, phys_dim, phys_dim)
        yield np.identity(phys_dim).reshape(1, phys_dim, phys_dim)

    return MatrixProductOperator(gen_arrays(), **mpo_opts)


def spin_ham_mpo_tensor(one_site_terms, two_site_terms, S=1 / 2, which=None):
    """Generate tensor(s) for a spin hamiltonian MPO.

    Parameters
    ----------
    one_site_terms : sequence of (scalar, operator)
        The terms that act on a single site, each ``operator`` can be a string
        suitable to be sent to :func:`spin_operator` or an actual 2d-array.
    two_site_terms : sequence of (scalar, operator operator)
        The terms that act on two neighbouring sites, each ``operator`` can be
        a string suitable to be sent to :func:`spin_operator` or an actual
        2d-array.
    S : fraction, optional
        What size spin to use, defaults to spin-1/2.
    which : {None, 'L', 'R', 'A'}, optional
        If ``None``, generate the middle tensor, if 'L' a left-end tensor, if
        'R' a right-end tensor and if 'A' all three.

    Returns
    -------
    numpy.ndarray{, numpy.ndarray, numpy.ndarray}
    """
    # local dimension
    D = int(2 * S + 1)
    # bond dimension
    B = len(two_site_terms) + 2

    H = np.zeros((B, B, D, D), dtype=complex)

    # add two-body terms
    for i, (factor, s1, s2) in enumerate(two_site_terms):
        if isinstance(s1, str):
            s1 = spin_operator(s1, S=S)
        if isinstance(s2, str):
            s2 = spin_operator(s2, S=S)
        H[1 + i, 0, :, :] = s1
        H[-1, 1 + i, :, :] = factor * s2

    # add one-body terms
    for factor, s in one_site_terms:
        if isinstance(s, str):
            s = spin_operator(s, S=S)
        H[B - 1, 0, :, :] += factor * s

    H[0, 0, :, :] = eye(D)
    H[B - 1, B - 1, :, :] = eye(D)

    make_immutable(H)

    if which == 'L':
        return H[-1, :, :, :]
    elif which == 'R':
        return H[:, 0, :, :]
    elif which == 'A':
        return H[-1, :, :, :], H, H[:, 0, :, :]

    return H


class MPOSpinHam:
    """Class for easily building translationally invariant spin hamiltonians in
    MPO form. Currently limited to nearest neighbour interactions (and single
    site terms).

    Parameters
    ----------
    S : float
        The type of spin.

    Example
    -------
    >>> builder = MPOSpinHam(S=3 / 2)
    >>> builder.add_term(-0.3, 'Z')
    >>> builder.add_term(0.5, '+', '-')
    >>> builder.add_term(0.5, '-', '+')
    >>> builder.add_term(1.0, 'Z', 'Z')
    >>> mpo_ham = builder.build(100)
    """

    def __init__(self, S=1 / 2):
        self.S = S
        self.one_site_terms = []
        self.two_site_terms = []

    def add_term(self, factor, *operators):
        """Add another term to the expression to be built.

        Parameters
        ----------
        factor : scalar
            Scalar factor to multiply this term by.
        *operators : str or array
            The operators to use. Can specify one or two for single or two site
            terms respectively. Can use strings, which are supplied to
            ``spin_operator``, or actual arrays as long as they have the
            correct dimension.
        """
        if len(operators) == 1:
            self.one_site_terms.append((factor, *operators))
        elif len(operators) == 2:
            self.two_site_terms.append((factor, *operators))
        else:
            raise NotImplementedError("3-body+ terms are not supported yet.")

    def build(self, n, upper_ind_id='k{}', lower_ind_id='b{}',
              site_tag_id='i{}', tags=None, bond_name=""):
        """Build an instance of this MPO of size ``n``. See also
        ``MatrixProductOperator``.
        """
        left, middle, right = spin_ham_mpo_tensor(
            self.one_site_terms, self.two_site_terms, S=self.S, which='A')

        arrays = (left, *[middle] * (n - 2), right)

        return MatrixProductOperator(arrays=arrays, bond_name=bond_name,
                                     upper_ind_id=upper_ind_id,
                                     lower_ind_id=lower_ind_id,
                                     site_tag_id=site_tag_id, tags=tags)


def MPO_ham_ising(n, j=1.0, bx=0.0,
                  upper_ind_id='k{}',
                  lower_ind_id='b{}',
                  site_tag_id='i{}',
                  tags=None,
                  bond_name=""):
    """Ising Hamiltonian in matrix product operator form.
    """
    H = MPOSpinHam(S=1 / 2)
    H.add_term(j, 'Z', 'Z')
    H.add_term(-bx, 'X')
    return H.build(n, site_tag_id=site_tag_id, tags=tags, bond_name=bond_name,
                   upper_ind_id=upper_ind_id, lower_ind_id=lower_ind_id)


def MPO_ham_XY(n, j=1.0, bz=0.0,
               upper_ind_id='k{}',
               lower_ind_id='b{}',
               site_tag_id='i{}',
               tags=None,
               bond_name=""):
    """XY-Hamiltonian in matrix product operator form.
    """
    H = MPOSpinHam(S=1 / 2)
    H.add_term(j, 'X', 'X')
    H.add_term(j, 'Y', 'Y')
    H.add_term(-bz, 'Z')
    return H.build(n, site_tag_id=site_tag_id, tags=tags, bond_name=bond_name,
                   upper_ind_id=upper_ind_id, lower_ind_id=lower_ind_id)


def MPO_ham_heis(n, j=1.0, bz=0.0,
                 upper_ind_id='k{}',
                 lower_ind_id='b{}',
                 site_tag_id='i{}',
                 tags=None,
                 bond_name=""):
    """Heisenberg Hamiltonian in matrix product operator form.
    """
    H = MPOSpinHam(S=1 / 2)
    H.add_term(j, 'X', 'X')
    H.add_term(j, 'Y', 'Y')
    H.add_term(j, 'Z', 'Z')
    H.add_term(-bz, 'Z')
    return H.build(n, site_tag_id=site_tag_id, tags=tags, bond_name=bond_name,
                   upper_ind_id=upper_ind_id, lower_ind_id=lower_ind_id)


def MPO_ham_mbl(n, dh, j=1.0, run=None, S=1 / 2, **mpo_opts):
    """The many-body-localized spin hamiltonian.

    Parameters
    ----------
    n : int
        Number of spins.
    dh : float
        Random noise strength.
    j : float, sequence of float
        Interaction strength(s) e.g. 1 or (1., 1., 0.5).
    run : int
        Random number to seed the noise with.
    S : float
        The underlying spin of the system, defaults to 1/2.
    mpo_opts
        Supplied to :class:`MatrixProductOperator`.
    """
    if run is not None:
        np.random.seed(run)

    try:
        jx, jy, jz = j
    except (TypeError, ValueError):
        jx = jy = jz = j

    interaction = [(jx, 'X', 'X'), (jy, 'Y', 'Y'), (jz, 'Z', 'Z')]

    def dhi():
        return dh * (2 * np.random.rand() - 1)

    def gen_arrays():
        yield spin_ham_mpo_tensor([(dhi(), 'Z')], interaction, which='L', S=S)
        for _ in range(n - 2):
            yield spin_ham_mpo_tensor([(dhi(), 'Z')], interaction, S=S)
        yield spin_ham_mpo_tensor([(dhi(), 'Z')], interaction, which='R', S=S)

    return MatrixProductOperator(gen_arrays(), **mpo_opts)
