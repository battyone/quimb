import functools
from math import sqrt
import numpy as np
import scipy.linalg as scla
import scipy.sparse.linalg as spla
try:
    from opt_einsum import contract as einsum
except ImportError:
    from numpy import einsum
from ..accel import prod


def int2tup(x):
    return (x if isinstance(x, tuple) else
            (x,) if isinstance(x, int) else
            tuple(x))


@functools.lru_cache(128)
def get_cntrct_inds_ptr_dot(ndim_ab, sysa):
    """Find the correct integer contraction labels for ``lazy_ptr_dot``.

    Parameters
    ----------
    ndim_ab : int
        The total number of subsystems (dimensions) in 'ab'.
    sysa : int or sequence of int, optional
            Index(es) of the 'a' subsystem(s) to keep.

    Returns
    -------
    inds_a_ket : sequence of int
        The tensor index labels for the ket on subsystem 'a'.
    inds_ab_bra : sequence of int
        The tensor index labels for the bra on subsystems 'ab'.
    inds_ab_ket : sequence of int
        The tensor index labels for the ket on subsystems 'ab'.
    """
    inds_a_ket = []
    inds_ab_bra = []
    inds_ab_ket = []

    upper_inds = iter(range(ndim_ab, 2 * ndim_ab))

    for i in range(ndim_ab):
        if i in sysa:
            inds_a_ket.append(i)
            inds_ab_bra.append(i)
            inds_ab_ket.append(next(upper_inds))
        else:
            inds_ab_bra.append(i)
            inds_ab_ket.append(i)

    return inds_a_ket, inds_ab_bra, inds_ab_ket


def lazy_ptr_dot(psi_ab, psi_a, dims=None, sysa=0):
    """Perform the 'lazy' evalution of ``ptr(psi_ab, ...) @ psi_a``,
    that is, contract the tensor diagram in an efficient way that does not
    necessarily construct the explicit reduced density matrix. In tensor
    diagram notation:
    ``
    +-------+
    | psi_a |   ______
    +_______+  /      \
       a|      |b     |
    +-------------+   |
    |  psi_ab.H   |   |
    +_____________+   |
                      |
    +-------------+   |
    |   psi_ab    |   |
    +_____________+   |
       a|      |b     |
        |      \______/
    ``

    Parameters
    ----------
    psi_ab : ket
        State to partially trace and dot with another ket, with
        size ``prod(dims)``.
    psi_a : ket
        State to act on with the dot product, of size ``prod(dims[sysa])``.
    dims : sequence of int, optional
        The sub dimensions of ``psi_ab``, inferred as bipartite if not given,
        i.e. ``(psi_a.size, psi_ab.size // psi_a.size)``.
    sysa : int or sequence of int, optional
        Index(es) of the 'a' subsystem(s) to keep.

    Returns
    -------
    ket
    """
    if dims is None:
        da = psi_a.size
        d = psi_ab.size
        dims = (da, d // da)

    # convert to tuple so can always cache
    sysa = int2tup(sysa)

    ndim_ab = len(dims)
    dims_a = [d for i, d in enumerate(dims) if i in sysa]

    inds_a_ket, inds_ab_bra, inds_ab_ket = get_cntrct_inds_ptr_dot(
        ndim_ab, sysa)

    psi_ab_tensor = np.asarray(psi_ab).reshape(dims)

    return einsum(
        np.asarray(psi_a).reshape(dims_a), inds_a_ket,
        psi_ab_tensor.conjugate(), inds_ab_bra,
        psi_ab_tensor, inds_ab_ket,
    ).reshape(psi_a.shape)


class LazyPtrOperatr(spla.LinearOperator):
    """A linear operator representing action of partially tracing a bipartite
    state, then multiplying another 'unipartite' state.

    Parameters
    ----------
    psi_ab : ket
        State to partially trace and dot with another ket, with
        size ``prod(dims)``.
    dims : sequence of int, optional
        The sub dimensions of ``psi_ab``.
    sysa : int or sequence of int, optional
        Index(es) of the 'a' subsystem(s) to keep.
    """

    def __init__(self, psi_ab, dims, sysa):
        self.psi_ab = psi_ab
        self.dims = dims
        self.sysa = int2tup(sysa)
        dims_a = [d for i, d in enumerate(dims) if i in self.sysa]
        sz_a = prod(dims_a)
        super().__init__(dtype=psi_ab.dtype, shape=(sz_a, sz_a))

    def _matvec(self, vec):
        return lazy_ptr_dot(self.psi_ab, vec, self.dims, self.sysa)

    def _adjoint(self):
        return self.__class__(self.psi_ab.conjugate(), self.dims, self.sysa)


@functools.lru_cache(128)
def get_cntrct_inds_ptr_ppt_dot(ndim_abc, sysa, sysb):
    """Find the correct integer contraction labels for ``lazy_ptr_ppt_dot``.

    Parameters
    ----------
    ndim_abc : int
        The total number of subsystems (dimensions) in 'abc'.
    sysa : int or sequence of int, optional
        Index(es) of the 'a' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).
    sysa : int or sequence of int, optional
        Index(es) of the 'b' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).

    Returns
    -------
    inds_ab_ket : sequence of int
        The tensor index labels for the ket on subsystems 'ab'.
    inds_abc_bra : sequence of int
        The tensor index labels for the bra on subsystems 'abc'.
    inds_abc_ket : sequence of int
        The tensor index labels for the ket on subsystems 'abc'.
    inds_out : sequence of int
        The tensor indices of the resulting ket, important as these might
        no longer be ordered.
    """
    inds_ab_ket = []
    inds_abc_bra = []
    inds_abc_ket = []
    inds_out = []

    upper_inds = iter(range(ndim_abc, 2 * ndim_abc))

    for i in range(ndim_abc):
        if i in sysa:
            up_ind = next(upper_inds)
            inds_ab_ket.append(i)
            inds_abc_bra.append(up_ind)
            inds_abc_ket.append(i)
            inds_out.append(up_ind)
        elif i in sysb:
            up_ind = next(upper_inds)
            inds_ab_ket.append(up_ind)
            inds_abc_bra.append(up_ind)
            inds_abc_ket.append(i)
            inds_out.append(i)
        else:
            inds_abc_bra.append(i)
            inds_abc_ket.append(i)

    return inds_ab_ket, inds_abc_bra, inds_abc_ket, inds_out


def lazy_ptr_ppt_dot(psi_abc, psi_ab, dims, sysa, sysb):
    """Perform the 'lazy' evalution of
    ``partial_transpose(ptr(psi_abc, ...)) @ psi_ab``, that is, contract the
    tensor diagram in an efficient way that does not necessarily construct
    the explicit reduced density matrix. For a tripartite system, the partial
    trace is with respect to ``c``, while the partial tranpose is with
    respect to ``a/b``. In tensor diagram notation:
    ``
    +--------------+
    |   psi_ab     |
    +______________+  _____
     a|  ____   b|   /     \
      | /   a\   |   |c    |
      | | +-------------+  |
      | | |  psi_abc.H  |  |
      \ / +-------------+  |
       X                   |
      / \ +-------------+  |
      | | |   psi_abc   |  |
      | | +-------------+  |
      | \____/a  |b  |c    |
     a|          |   \_____/
    ``

    Parameters
    ----------
    psi_abc : ket
        State to partially trace, partially tranpose, then dot with another
        ket, with size ``prod(dims)``.
    psi_ab : ket
        State to act on with the dot product, of size
        ``prod(dims[sysa] + dims[sysb])``.
    dims : sequence of int
        The sub dimensions of ``psi_abc``.
    sysa : int or sequence of int, optional
        Index(es) of the 'a' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).
    sysa : int or sequence of int, optional
        Index(es) of the 'b' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).

    Returns
    -------
    ket
    """
    # convert to tuple so can always cache
    sysa, sysb = int2tup(sysa), int2tup(sysb)

    inds_ab_ket, inds_abc_bra, inds_abc_ket, inds_out = \
        get_cntrct_inds_ptr_ppt_dot(len(dims), sysa, sysb)

    psi_abc_tensor = np.asarray(psi_abc).reshape(dims)
    dims_ab = [d for i, d in enumerate(dims) if (i in sysa) or (i in sysb)]

    # must have ``inds_out`` as resulting indices are not ordered
    # in the same way as input due to partial tranpose.
    return einsum(
        np.asarray(psi_ab).reshape(dims_ab), inds_ab_ket,
        psi_abc_tensor.conjugate(), inds_abc_bra,
        psi_abc_tensor, inds_abc_ket,
        inds_out,
    ).reshape(psi_ab.shape)


class LazyPtrPptOperator(spla.LinearOperator):
    """A linear operator representing action of partially tracing a tripartite
    state, partially transposing the remaining bipartite state, then
    multiplying another bipartite state.

    Parameters
    ----------
    psi_abc : ket
        State to partially trace, partially tranpose, then dot with another
        ket, with size ``prod(dims)``.
        ``prod(dims[sysa] + dims[sysb])``.
    dims : sequence of int
        The sub dimensions of ``psi_abc``.
    sysa : int or sequence of int, optional
        Index(es) of the 'a' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).
    sysa : int or sequence of int, optional
        Index(es) of the 'b' subsystem(s) to keep, with respect to all
        the dimensions, ``dims``, (i.e. pre-partial trace).
    """

    def __init__(self, psi_abc, dims, sysa, sysb):
        self.psi_abc = psi_abc
        self.dims = dims
        self.sysa, self.sysb = int2tup(sysa), int2tup(sysb)
        sys_ab = self.sysa + self.sysb
        sz_ab = prod([d for i, d in enumerate(dims) if i in sys_ab])
        super().__init__(dtype=psi_abc.dtype, shape=(sz_ab, sz_ab))

    def _matvec(self, vec):
        return lazy_ptr_ppt_dot(self.psi_abc, vec, self.dims,
                                self.sysa, self.sysb)

    def _adjoint(self):
        return self.__class__(self.psi_abc.conjugate(), self.dims,
                              self.sysa, self.sysb)


def construct_lanczos_tridiag(A, v0=None, M=20):
    """Construct the tridiagonal lanczos matrix using only matvec operators.

    Parameters
    ----------
    A : matrix-like or linear operator
        The operator to approximate, must implement ``.dot`` method to compute
        its action on a vector.
    v0 : vector, optional
        The starting vector to iterate with, default to random.
    M : int, optional
        The number of iterations and thus rank of the matrix to find.

    Returns
    -------
    alpha : sequence of float of length k
        The diagonal entries of the lanczos matrix.
    beta : sequence of float of length k - 1
        The off-diagonal entries of the lanczos matrix.
    """
    if isinstance(A, np.matrix):
        A = np.asarray(A)

    d = A.shape[0]

    alpha = np.zeros(M + 1)
    beta = np.zeros(M + 2)
    vk = np.empty((d, M + 2), dtype=np.complex128)
    vk[:, 0] = 0.0j

    # initialize & normalize the starting vector
    if v0 is None:
        vk[:, 1] = np.random.randn(d)
        vk[:, 1] += 1.0j * np.random.randn(d)
    else:
        vk[:, 1] = v0
    vk[:, 1] /= sqrt(np.vdot(vk[:, 1], vk[:, 1]).real)

    # construct the krylov subspace
    for k in range(1, M + 1):
        wk = A.dot(vk[:, k]) - beta[k] * vk[:, k - 1]
        alpha[k] = np.vdot(wk, vk[:, k]).real
        wk -= alpha[k] * vk[:, k]
        beta[k + 1] = sqrt(np.vdot(wk, wk).real)
        vk[:, k + 1] = wk / beta[k + 1]

    return alpha[1:], beta[2:-1]


def lanczos_tridiag_eig(alpha, beta):
    """Find the eigen-values and -vectors of the Lanczos triadiagonal matrix.
    """
    Tk_banded = np.empty((2, alpha.size))
    Tk_banded[0, :] = alpha
    Tk_banded[1, :-1] = beta
    return scla.eig_banded(Tk_banded, lower=True)


def approx_spectral_function(A, fn, M=20, R=10, v0=None):
    """Approximate a spectral function, that is, the quantity ``Tr(fn(A))``.
    """

    def gen_vals():
        for _ in range(R):
            alpha, beta = construct_lanczos_tridiag(A, M=M, v0=v0)
            el, ev = lanczos_tridiag_eig(alpha, beta)

            for i in range(M):
                yield fn(el[i]) * ev[0, i]**2

    return sum(gen_vals()) * (A.shape[0] / R)
