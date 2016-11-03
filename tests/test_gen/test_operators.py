import pytest
import numpy as np
from numpy.testing import assert_allclose
from quimb import (
    issparse,
    eigvals,
    eigvecs,
    groundstate,
    overlap,
    singlet,
    seigvals,
    sig,
    controlled,
    ham_heis,
    ham_j1j2,
    zspin_projector,
)


class TestSig:
    def test_sig_dim2(self):
        for dir in (1, 'x', 'X',
                    2, 'y', 'Y',
                    3, 'z', 'Z'):
            x = sig(dir)
            assert_allclose(eigvals(x), [-1, 1])

    def test_sig_dim3(self):
        for dir in (1, 'x', 'X',
                    2, 'y', 'Y',
                    3, 'z', 'Z'):
            x = sig(dir, dim=3)
            assert_allclose(eigvals(x), [-1, 0, 1],
                            atol=1e-15)

    def test_sig_bad_dim(self):
        with pytest.raises(KeyError):
            sig('x', 4)

    def test_sig_bad_dir(self):
        with pytest.raises(KeyError):
            sig('w', 2)


class TestControlledZ:
    def test_controlled_z_dense(self):
        cz = controlled('z')
        assert_allclose(cz, np.diag([1, 1, 1, -1]))

    def test_controlled_z_sparse(self):
        cz = controlled('z', sparse=True)
        assert(issparse(cz))
        assert_allclose(cz.A, np.diag([1, 1, 1, -1]))


class TestHamHeis:
    def test_ham_heis_2(self):
        h = ham_heis(2, cyclic=False)
        evals = eigvals(h)
        assert_allclose(evals, [-3, 1, 1, 1])
        gs = groundstate(h)
        assert_allclose(overlap(gs, singlet()), 1.)

    def test_ham_heis_sparse_cyclic_4(self):
        h = ham_heis(4, sparse=True, cyclic=True)
        lk = seigvals(h, 4)
        assert_allclose(lk, [-8, -4, -4, -4])

    def test_ham_heis_bz(self):
        h = ham_heis(2, cyclic=False, bz=2)
        evals = eigvals(h)
        assert_allclose(evals, [-3, -3, 1, 5])

    @pytest.mark.parametrize("stype", ["coo", "csr", "csc", "bsr"])
    def test_sformat_construct(self, stype):
        h = ham_heis(4, sparse=True, stype=stype)
        assert h.format == stype


class TestHamJ1J2:
    def test_ham_j1j2_3_dense(self):
        h = ham_j1j2(3, j2=1.0, cyclic=False)
        h2 = ham_heis(3, cyclic=True)
        assert_allclose(h, h2)

    def test_ham_j1j2_6_sparse_cyc(self):
        h = ham_j1j2(6, j2=0.5, sparse=True, cyclic=True)
        lk = seigvals(h, 5)
        assert_allclose(lk, [-9, -9, -7, -7, -7])

    def test_ham_j1j2_4_bz(self):
        h = ham_j1j2(4, j2=0.5, cyclic=True, bz=0)
        lk = seigvals(h, 11)
        assert_allclose(lk, [-6, -6, -2, -2, -2, -2, -2, -2, -2, -2, -2])
        h = ham_j1j2(4, j2=0.5, cyclic=True, bz=0.1)
        lk = seigvals(h, 11)
        assert_allclose(lk, [-6, -6, -2.2, -2.2, -2.2,
                             -2.0, -2.0, -2.0, -1.8, -1.8, -1.8])


class TestSpinZProjector:
    @pytest.mark.parametrize("sz", [-2, -1, 0, 1, 2])
    def test_works(self, sz):
        prj = zspin_projector(4, sz)
        h = ham_heis(4)
        h0 = prj @ h @ prj.H
        v0s = eigvecs(h0)
        for v0 in v0s.T:
            vf = prj.H @ v0.T
            prjv = vf @ vf.H
            # Check reconstructed full eigenvectors commute with full ham
            assert_allclose(prjv @ h, h @ prjv, atol=1e-13)
        if sz == 0:
            # Groundstate must be in most symmetric subspace
            gs = groundstate(h)
            gs0 = prj .H @ v0s[:, 0]
            assert_allclose(overlap(gs, gs0), 1.0)
            assert_allclose(overlap(h, gs0), overlap(h, gs))

    def test_raises(self):
        with pytest.raises(ValueError):
            zspin_projector(5, 0)
        with pytest.raises(ValueError):
            zspin_projector(4, 1 / 2)

    @pytest.mark.parametrize("sz", [(-1 / 2, 1 / 2), (3 / 2, 5 / 2)])
    def test_spin_half_double_space(self, sz):
        prj = zspin_projector(5, sz)
        h = ham_heis(5)
        h0 = prj @ h @ prj.H
        v0s = eigvecs(h0)
        for v0 in v0s.T:
            vf = prj.H @ v0.T
            prjv = vf @ vf.H
            # Check reconstructed full eigenvectors commute with full ham
            assert_allclose(prjv @ h, h @ prjv, atol=1e-13)
        if sz == 0:
            # Groundstate must be in most symmetric subspace
            gs = groundstate(h)
            gs0 = prj .H @ v0s[:, 0]
            assert_allclose(overlap(gs, gs0), 1.0)
            assert_allclose(overlap(h, gs0), overlap(h, gs))