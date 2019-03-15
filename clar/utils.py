import numpy as np

from numba import njit
from numpy.linalg import norm
from numpy.linalg import solve


# @njit
def sqrtm(ZZT):
    """Take the square root of a symetrique definite matrix.

    Output: (float,  np.array, shape (n_sensors, n_sensors))
        (trace of Sigma updated, inverse of Sigma updated)
     """
    eigvals, eigvecs = np.linalg.eigh(ZZT)
    eigvals = np.maximum(0, eigvals)
    eigvals = np.sqrt(eigvals)
    eigvals = np.expand_dims(eigvals, axis=1)
    return eigvecs @ (eigvals * eigvecs.T)


def get_S_Sinv(ZZT, sigma_min=1e-6):
    """Take the square root and inverse of squre root of a symetrique definite matrix.

    Output: (float,  np.array, shape (n_sensors, n_sensors))
        (trace of Sigma updated, inverse of Sigma updated)
     """
    eigvals, eigvecs = np.linalg.eigh(ZZT)
    eigvals = np.maximum(0, eigvals)
    eigvals = np.sqrt(eigvals)
    div_eigvals = 1 / eigvals
    mask = (eigvals < sigma_min * eigvals.max())

    print(eigvals)
    print('Number of eigvals clipped: %d' % mask.sum())
    div_eigvals[mask] = 0
    eigvals = np.expand_dims(eigvals, axis=1)
    div_eigvals = np.expand_dims(div_eigvals, axis=1)
    return eigvecs @ (eigvals * eigvecs.T), eigvecs @ (div_eigvals * eigvecs.T)


@njit
def BST(u, tau):
    """
    BST stands for block soft thresholding operator.

    Parameters
    ----------------------
    u: numpy array
    tau: non*negativ number

    Output
    ---------------------
    numpy array:
        vector of the same size as u

    line_is_zero: bool
        Whether or not the block soft thresholding returns a vector full of 0.
    """
    a = 1 - tau / norm(u)
    line_is_zero = a < 0
    if a < 0:
        u.fill(0)
    else:
        u *= a
    return u, line_is_zero


@njit
def condition_better(ZZT, sigma_min):
    """Update Sigma by conditionning it better.

    Output: (float,  np.array, shape (n_sensors, n_sensors))
        (trace of Sigma updated, inverse of Sigma updated)
     """
    eigvals, eigvecs = np.linalg.eigh(ZZT)

    n_eigvals_clipped = (eigvals < sigma_min).sum()
    bool_reach_sigma_min = n_eigvals_clipped > 0

    eigvals = np.maximum(0, eigvals)
    eigvals = np.maximum(np.sqrt(eigvals), sigma_min)
    eigvals = np.expand_dims(eigvals, axis=1)
    return eigvals.sum(), \
        eigvecs @ (1 / eigvals * eigvecs.T)


@njit
def l_2_inf(A):
    """Compute the l_2_inf norm of a matrix A.

    Parameters:
    ----------
    A: np.array

    Output:
    -------
    float
        the l_2_inf norm of A
    """
    res = 0.
    # row_norm = 0.
    for j in range(A.shape[0]):
        res = max(res, norm(A[j, :]))
    return res
    # return norm(A, axis=1, ord=2).max()


@njit
def l_2_1(A):
    """Compute the l_2_1 norm of a matrix A.

    Parameters:
    ----------
    A: np.array

    Output:
    -------
    float
        the l_2_1 norm of A
    """
    res = 0.
    for j in range(A.shape[0]):
        res += norm(A[j, :])
    return res
    # return norm(A, axis=1, ord=2).sum()


def get_alpha_max_mtl(X, Y):
    n_sensors, n_times = Y.shape
    alpha_max = l_2_inf(X.T @ Y) / (n_times * n_sensors)
    return alpha_max


def get_alpha_max(X, Y, sigma_min, pb_name):
    if pb_name == "SGCL":
        assert Y.ndim == 2
        return get_alpha_max_sgcl(X, Y, sigma_min)
    elif pb_name == "CLAR":
        return get_alpha_max_me(X, Y, sigma_min)
    elif pb_name == "MTL":
        return get_alpha_max_mtl(X, Y)
    elif pb_name == "MTLME":
        observations = Y.transpose((1, 0, 2))
        observations = observations.reshape(observations.shape[0], -1)
        return get_alpha_max_mtl(X, observations)
    else:
        raise NotImplementedError("No solver '{}' in this module"
                                  .format(pb_name))


def get_alpha_max_sgcl(X, Y, sigma_min):
    """Function to compute the maximal alpha before obtaining all zeros.
    """
    n_sensors, n_times = Y.shape
    _, Sigma_max_inv = condition_better(
        Y @ Y.T / n_times, sigma_min)
    result = l_2_inf(X.T @ Sigma_max_inv @ Y)
    result /= (n_sensors * n_times)
    return result


def get_alpha_max_me(X, all_epochs, sigma_min):
    """Function to compute the maximal alpha before obtaining all zeros.
    """
    n_epochs, n_sensors, n_times = all_epochs.shape
    Y = all_epochs.mean(axis=0)

    cov_Yl = 0
    for l in range(n_epochs):
        cov_Yl += all_epochs[l, :, :] @ all_epochs[l, :, :].T
    cov_Yl /= (n_epochs * n_times)

    _, Sigma_max_inv = condition_better(
        cov_Yl, sigma_min)
    result = l_2_inf(X.T @ Sigma_max_inv @ Y)
    result /= (n_sensors * n_times)
    return result


def get_sigma_min_and_alpha(X, Y):
    sigma_min = norm(Y) / (np.sqrt(Y.shape[1] * Y.shape[0]) * 1000)
    alpha = get_alpha_max(X, Y, sigma_min) / 10
    return sigma_min, alpha


def get_sigma_min(Y):
    sigma_min = norm(Y, ord='fro') / (np.sqrt(Y.shape[1] * Y.shape[0]) * 1000)
    return sigma_min


def get_relative_error(
        Sigma_hat, Sigma_star, ord='fro'):
    res = norm(Sigma_hat - Sigma_star, ord=ord) / norm(Sigma_star, ord=ord)
    return res


def get_relative_log_res(
        X, Y, B_star, Sigma_inv_star, B_hat, Sigma_inv_hat, me=False):
    if me:
        res = get_norm_res_me(X, Y, B_hat, Sigma_inv_hat) / \
            get_norm_res_me(X, Y, B_star, Sigma_inv_star)
    else:
        res = get_norm_res(X, Y, B_hat, Sigma_inv_hat) / \
            get_norm_res(X, Y, B_star, Sigma_inv_star)
    return np.log10(res)


def get_norm_res(X, Y, B, Sigma_inv, ord='fro'):
    R = Y - X @ B
    res = norm(R.T @ (Sigma_inv @ R), ord=ord)
    return res


def get_norm_res_me(X, all_epochs, B, Sigma_inv, ord='fro'):
    R = all_epochs - X @ B
    n_epochs, n_sensors, n_times = R.shape
    res = 0
    for l in range(n_epochs):
        res += norm(R[l, :, :].T @ Sigma_inv @ R[l, :, :], ord=ord)
    return res
