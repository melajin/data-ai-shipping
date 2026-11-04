"""Small NumPy models for the synthetic trajectory learning experiment.

Every fit must receive only the split named by the caller's data contract:
preprocessing, classifier gradients and anomaly statistics use train; classifier
checkpoint choice uses validation; temperature fitting uses calibration. None
of these synthetic scores is an accident probability.
"""

from __future__ import annotations

from collections.abc import Mapping
import math

import numpy as np


STATE_VERSION = 1
TEMPERATURE_GRID = np.geomspace(0.1, 10.0, 81)


def _integer(value, name, minimum=0):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _number(value, name, minimum=None, positive=False):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite and positive")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _matrix(X, name="X", n_features=None, allow_nan=False, allow_empty=True):
    try:
        result = np.asarray(X, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a numeric matrix") from exc
    if result.ndim != 2 or result.shape[1] == 0:
        raise ValueError(f"{name} must have shape (n_samples, n_features), n_features > 0")
    if n_features is not None and result.shape[1] != n_features:
        raise ValueError(f"{name} has an incompatible feature dimension")
    if not allow_empty and result.shape[0] == 0:
        raise ValueError(f"{name} must contain at least one row")
    invalid = np.isinf(result) if allow_nan else ~np.isfinite(result)
    if invalid.any():
        raise ValueError(f"{name} contains nonfinite values")
    return result


def _valid_labels(y, n_rows, n_classes):
    """Mask before converting labels to integers or using them as indices."""
    try:
        values = np.asarray(y, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("y must be a numeric one-dimensional label array") from exc
    if values.ndim != 1 or values.shape[0] != n_rows:
        raise ValueError("y must have shape (n_samples,)")
    mask = np.isfinite(values)
    mask &= (values >= 0) & (values < n_classes)
    # Only finite, in-range values reach the integer test and conversion.
    mask[mask] = values[mask] == np.floor(values[mask])
    if not mask.any():
        raise ValueError("at least one valid label is required")
    return mask, values[mask].astype(np.int64)


def _state(state, kind):
    if not isinstance(state, Mapping):
        raise ValueError("model state must be an object")
    version = state.get("schema_version")
    if (isinstance(version, bool) or not isinstance(version, int)
            or state.get("type") != kind or version != STATE_VERSION):
        raise ValueError(f"unsupported {kind} state type or schema version")
    return state


def _array(state, key, shape):
    if key not in state:
        raise ValueError(f"model state is missing {key}")
    try:
        values = np.asarray(state[key], dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"model state {key} must be numeric") from exc
    if values.shape != shape or not np.isfinite(values).all():
        raise ValueError(f"model state {key} has invalid shape or nonfinite values")
    return values.copy()


def _required(state, key):
    if key not in state:
        raise ValueError(f"model state is missing {key}")
    return state[key]


def softmax(logits, temperature=1.0):
    """Stable row-wise probabilities for finite logits of shape (N, C).

    Subtraction happens before division by the positive temperature. Thus a
    large common offset does not overflow merely because temperature is small.
    """
    values = _matrix(logits, "logits")
    temperature = _number(temperature, "temperature", positive=True)
    if values.shape[0] == 0:
        return values.copy()
    with np.errstate(over="ignore", under="ignore"):
        centered = (values - values.max(axis=1, keepdims=True)) / temperature
        exponentials = np.exp(centered)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _nll_from_logits(logits, labels, temperature=1.0):
    """Mean log-sum-exp cross entropy; labels have already been validated."""
    with np.errstate(over="ignore", under="ignore"):
        centered = (logits - logits.max(axis=1, keepdims=True)) / temperature
        log_normalizer = np.log(np.exp(centered).sum(axis=1))
        losses = log_normalizer - centered[np.arange(labels.size), labels]
    result = float(np.mean(losses))
    if not math.isfinite(result):
        raise ValueError("nonfinite NLL; feature or parameter magnitudes are too large")
    return result


class Preprocessor:
    """Train median imputation, population scaling, then missing indicators.

    Input shape is (N, D), with NaN for missing values and no infinities. Output
    shape is (N, 2D): filled/scaled geometry columns followed by the original
    NaN mask as floats. Statistics are never updated by ``transform``. A column
    missing in every training row has median=mean=0 and scale=1; a constant
    observed column also has scale=1.
    """

    def __init__(self):
        self.n_features_ = None

    def fit(self, X):
        values = _matrix(X, allow_nan=True, allow_empty=False)
        n_features = values.shape[1]
        medians = np.zeros(n_features, dtype=np.float64)
        all_missing = np.isnan(values).all(axis=0)
        for column in np.flatnonzero(~all_missing):
            medians[column] = np.median(values[~np.isnan(values[:, column]), column])
        filled = np.where(np.isnan(values), medians, values)
        with np.errstate(over="ignore", invalid="ignore"):
            means = filled.mean(axis=0)
            scales = filled.std(axis=0, ddof=0)
        if not np.isfinite(means).all() or not np.isfinite(scales).all():
            raise ValueError("preprocessing statistics overflowed")
        scales[scales == 0] = 1.0
        means[all_missing] = 0.0
        scales[all_missing] = 1.0
        self.n_features_ = n_features
        self.medians_ = medians
        self.means_ = means
        self.scales_ = scales
        self.all_missing_ = all_missing
        return self

    def transform(self, X):
        if self.n_features_ is None:
            raise ValueError("preprocessor must be fitted before transform")
        values = _matrix(X, n_features=self.n_features_, allow_nan=True)
        missing = np.isnan(values)
        filled = np.where(missing, self.medians_, values)
        with np.errstate(over="ignore", invalid="ignore"):
            scaled = (filled - self.means_) / self.scales_
        if not np.isfinite(scaled).all():
            raise ValueError("preprocessing transform overflowed")
        return np.concatenate((scaled, missing.astype(np.float64)), axis=1)

    def to_dict(self):
        if self.n_features_ is None:
            raise ValueError("preprocessor must be fitted before serialization")
        return {
            "type": "preprocessor", "schema_version": STATE_VERSION,
            "n_features": self.n_features_, "medians": self.medians_.tolist(),
            "means": self.means_.tolist(), "scales": self.scales_.tolist(),
            "all_missing": self.all_missing_.tolist(),
            "output_order": "scaled_features_then_missing_mask",
        }

    @classmethod
    def from_dict(cls, state):
        state = _state(state, "preprocessor")
        n_features = _integer(_required(state, "n_features"), "n_features", 1)
        if state.get("output_order") != "scaled_features_then_missing_mask":
            raise ValueError("unsupported preprocessing output order")
        result = cls()
        result.medians_ = _array(state, "medians", (n_features,))
        result.means_ = _array(state, "means", (n_features,))
        result.scales_ = _array(state, "scales", (n_features,))
        if np.any(result.scales_ <= 0):
            raise ValueError("preprocessing scales must be positive")
        all_missing = _required(state, "all_missing")
        if not isinstance(all_missing, list) or len(all_missing) != n_features:
            raise ValueError("all_missing must be a boolean list with n_features entries")
        if any(not isinstance(value, bool) for value in all_missing):
            raise ValueError("all_missing entries must be boolean")
        result.all_missing_ = np.asarray(all_missing, dtype=bool)
        missing = result.all_missing_
        if (np.any(result.medians_[missing] != 0) or np.any(result.means_[missing] != 0)
                or np.any(result.scales_[missing] != 1)):
            raise ValueError("all-missing columns require median=mean=0 and scale=1")
        result.n_features_ = n_features
        return result


class Classifier:
    """Full-batch linear softmax or 16-unit tanh classifier using NumPy.

    ``params`` contains W,b for a linear model or W1,b1,W2,b2 for a hidden
    model. The objective is mean valid-label NLL plus l2/2 * sum(W**2); biases
    are not penalized. X has shape (N, input_dim), y has shape (N,). Missing or
    invalid labels are removed before indexing, and division uses their valid
    count. Validation NLL selects a checkpoint after each epoch; final weights
    are restored to the best epoch in ``history``.
    """

    def __init__(self, input_dim, n_classes=3, hidden=0, l2=0.01, seed=42):
        self.input_dim = _integer(input_dim, "input_dim", 1)
        self.n_classes = _integer(n_classes, "n_classes", 2)
        self.hidden = _integer(hidden, "hidden")
        if self.hidden not in (0, 16):
            raise ValueError("hidden must be 0 (linear) or 16 (tanh)")
        self.l2 = _number(l2, "l2", minimum=0)
        self.seed = _integer(seed, "seed")
        rng = np.random.default_rng(self.seed)
        if self.hidden:
            self.params = {
                "W1": rng.normal(0, 1 / math.sqrt(self.input_dim), (self.input_dim, self.hidden)),
                "b1": np.zeros(self.hidden),
                "W2": rng.normal(0, 1 / math.sqrt(self.hidden), (self.hidden, self.n_classes)),
                "b2": np.zeros(self.n_classes),
            }
        else:
            self.params = {
                "W": rng.normal(0, 1 / math.sqrt(self.input_dim), (self.input_dim, self.n_classes)),
                "b": np.zeros(self.n_classes),
            }
        self.best_epoch = None
        self.history = []

    def _forward(self, X):
        with np.errstate(over="ignore", invalid="ignore"):
            if self.hidden:
                hidden_values = np.tanh(X @ self.params["W1"] + self.params["b1"])
                logits = hidden_values @ self.params["W2"] + self.params["b2"]
            else:
                hidden_values = None
                logits = X @ self.params["W"] + self.params["b"]
        if not np.isfinite(logits).all():
            raise ValueError("nonfinite logits; feature or parameter magnitudes are too large")
        return logits, hidden_values

    def predict_logits(self, X):
        """Return finite logits of shape (N, n_classes), without fitting."""
        values = _matrix(X, n_features=self.input_dim)
        return self._forward(values)[0]

    def _regularization(self):
        if self.l2 == 0:
            return 0.0
        with np.errstate(over="ignore", invalid="ignore"):
            result = 0.5 * self.l2 * sum(float(np.sum(value * value))
                                       for key, value in self.params.items() if key.startswith("W"))
        if not math.isfinite(result):
            raise ValueError("regularization overflowed")
        return result

    def loss_and_gradients(self, X, y):
        """Return (mean valid-label NLL + l2/2 sum(W**2), parameter gradients).

        X is finite (N, input_dim); y is (N,). Invalid labels, including -1 and
        NaN, are excluded before any class index is formed. A batch with zero
        valid labels raises ValueError. Each gradient has its parameter's shape.
        """
        values = _matrix(X, n_features=self.input_dim)
        mask, labels = _valid_labels(y, values.shape[0], self.n_classes)
        values = values[mask]
        logits, hidden_values = self._forward(values)
        loss = _nll_from_logits(logits, labels) + self._regularization()
        delta = softmax(logits)
        delta[np.arange(labels.size), labels] -= 1.0
        delta /= labels.size
        with np.errstate(over="ignore", invalid="ignore"):
            if self.hidden:
                grad_w2 = hidden_values.T @ delta + self.l2 * self.params["W2"]
                grad_b2 = delta.sum(axis=0)
                delta_hidden = (delta @ self.params["W2"].T) * (1.0 - hidden_values**2)
                gradients = {
                    "W1": values.T @ delta_hidden + self.l2 * self.params["W1"],
                    "b1": delta_hidden.sum(axis=0), "W2": grad_w2, "b2": grad_b2,
                }
            else:
                gradients = {
                    "W": values.T @ delta + self.l2 * self.params["W"],
                    "b": delta.sum(axis=0),
                }
        if not math.isfinite(loss) or any(not np.isfinite(g).all() for g in gradients.values()):
            raise ValueError("loss or gradients overflowed")
        return float(loss), gradients

    def fit(self, X, y, X_val, y_val, epochs=400, learning_rate=0.03, patience=35):
        """Full-batch GD; return epoch/train_nll/val_nll/train_objective history.

        NLL and objective are evaluated after each parameter update. An epoch
        improves iff its validation NLL is strictly smaller. After ``patience``
        consecutive non-improving epochs, restore the best recorded checkpoint.
        At most 400 epochs are allowed for this CPU demonstration.
        """
        values = _matrix(X, n_features=self.input_dim, allow_empty=False)
        validation = _matrix(X_val, "X_val", self.input_dim, allow_empty=False)
        train_mask, train_labels = _valid_labels(y, values.shape[0], self.n_classes)
        val_mask, val_labels = _valid_labels(y_val, validation.shape[0], self.n_classes)
        values = values[train_mask]
        validation = validation[val_mask]
        epochs = _integer(epochs, "epochs", 1)
        if epochs > 400:
            raise ValueError("epochs must not exceed 400 for the sample system")
        learning_rate = _number(learning_rate, "learning_rate", positive=True)
        patience = _integer(patience, "patience", 1)
        original = {key: value.copy() for key, value in self.params.items()}
        best_parameters = None
        best_nll = math.inf
        best_epoch = None
        stale = 0
        history = []
        try:
            for epoch in range(1, epochs + 1):
                _, gradients = self.loss_and_gradients(values, train_labels)
                with np.errstate(over="ignore", invalid="ignore"):
                    updated = {key: value - learning_rate * gradients[key]
                               for key, value in self.params.items()}
                if any(not np.isfinite(value).all() for value in updated.values()):
                    raise ValueError("parameter update overflowed")
                self.params = updated
                train_nll = _nll_from_logits(self.predict_logits(values), train_labels)
                val_nll = _nll_from_logits(self.predict_logits(validation), val_labels)
                train_objective = _number(train_nll + self._regularization(), "train_objective")
                history.append({"epoch": epoch, "train_nll": train_nll,
                                "val_nll": val_nll,
                                "train_objective": train_objective})
                if val_nll < best_nll:
                    best_nll = val_nll
                    best_epoch = epoch
                    best_parameters = {key: value.copy() for key, value in self.params.items()}
                    stale = 0
                else:
                    stale += 1
                if stale >= patience:
                    break
        except (ValueError, FloatingPointError):
            self.params = original
            raise
        self.params = best_parameters
        self.best_epoch = best_epoch
        self.history = [dict(row) for row in history]
        return history

    def to_dict(self):
        return {
            "type": "classifier", "schema_version": STATE_VERSION,
            "input_dim": self.input_dim, "n_classes": self.n_classes,
            "hidden": self.hidden, "l2": self.l2, "seed": self.seed,
            "params": {key: value.tolist() for key, value in self.params.items()},
            "best_epoch": self.best_epoch, "history": [dict(row) for row in self.history],
            "objective": "mean_valid_label_nll_plus_half_l2_weight_squared_norm",
        }

    @classmethod
    def from_dict(cls, state):
        state = _state(state, "classifier")
        result = cls(_required(state, "input_dim"), _required(state, "n_classes"),
                     _required(state, "hidden"), _required(state, "l2"), _required(state, "seed"))
        if state.get("objective") != "mean_valid_label_nll_plus_half_l2_weight_squared_norm":
            raise ValueError("unsupported classifier objective")
        parameters = _required(state, "params")
        if not isinstance(parameters, Mapping) or set(parameters) != set(result.params):
            raise ValueError("classifier parameters do not match its architecture")
        result.params = {key: _array(parameters, key, value.shape)
                         for key, value in result.params.items()}
        history = _required(state, "history")
        if not isinstance(history, list) or len(history) > 400:
            raise ValueError("classifier history must be a list of at most 400 epochs")
        checked_history = []
        for index, row in enumerate(history, start=1):
            if not isinstance(row, Mapping) or set(row) != {"epoch", "train_nll", "val_nll", "train_objective"}:
                raise ValueError("invalid classifier history row")
            if _integer(row["epoch"], "history epoch", 1) != index:
                raise ValueError("classifier history epochs must be consecutive")
            checked = {"epoch": index}
            for key in ("train_nll", "val_nll", "train_objective"):
                checked[key] = _number(row[key], key, minimum=0)
            if checked["train_objective"] + 1e-12 < checked["train_nll"]:
                raise ValueError("train_objective must include train_nll")
            checked_history.append(checked)
        best_epoch = _required(state, "best_epoch")
        if checked_history:
            best_epoch = _integer(best_epoch, "best_epoch", 1)
            expected_epoch = min(checked_history, key=lambda row: row["val_nll"])["epoch"]
            if best_epoch != expected_epoch:
                raise ValueError("best_epoch must select the minimum validation NLL")
        elif best_epoch is not None:
            raise ValueError("best_epoch requires training history")
        result.best_epoch = best_epoch
        result.history = checked_history
        return result


def classification_metrics(y, probs):
    """Return accuracy, all-class macro F1, NLL, Brier, confusion and support.

    Confusion rows are true classes and columns predicted classes. Support is a
    list of valid-label counts by class. An absent class contributes F1=0.
    Multiclass Brier is mean(sum((p-one_hot(y))**2, axis=1)), without dividing
    by the number of classes. NLL clips an exact zero to the float64 positive
    normal minimum. Invalid labels are removed before one-hot/index operations.
    """
    probabilities = _matrix(probs, "probs")
    n_classes = probabilities.shape[1]
    if n_classes < 2 or np.any(probabilities < 0) or np.any(probabilities > 1):
        raise ValueError("probs must contain class probabilities in [0, 1]")
    if not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0, atol=1e-7):
        raise ValueError("each probability row must sum to one")
    mask, labels = _valid_labels(y, probabilities.shape[0], n_classes)
    probabilities = probabilities[mask]
    predicted = probabilities.argmax(axis=1)
    confusion = np.zeros((n_classes, n_classes), dtype=np.int64)
    np.add.at(confusion, (labels, predicted), 1)
    support = confusion.sum(axis=1)
    predicted_support = confusion.sum(axis=0)
    denominator = support + predicted_support
    f1 = np.divide(2.0 * np.diag(confusion), denominator,
                   out=np.zeros(n_classes), where=denominator > 0)
    chosen = np.maximum(probabilities[np.arange(labels.size), labels], np.finfo(np.float64).tiny)
    target = np.zeros_like(probabilities)
    target[np.arange(labels.size), labels] = 1.0
    return {
        "accuracy": float(np.mean(predicted == labels)),
        "macro_f1": float(np.mean(f1)), "nll": float(-np.mean(np.log(chosen))),
        "brier": float(np.mean(np.sum((probabilities - target)**2, axis=1))),
        "confusion": confusion.tolist(), "support": support.tolist(),
    }


def fit_temperature(logits, y):
    """Choose one positive temperature using calibration NLL only.

    The fixed 81-point logarithmic grid spans [0.1, 10], with T=1 explicitly
    included. The baseline is kept in a tie. The caller keeps calibration rows
    separate from candidate selection and final evaluation.
    """
    values = _matrix(logits, "logits", allow_empty=False)
    if values.shape[1] < 2:
        raise ValueError("temperature fitting requires at least two classes")
    mask, labels = _valid_labels(y, values.shape[0], values.shape[1])
    values = values[mask]
    best_temperature = 1.0
    best_nll = _nll_from_logits(values, labels)
    for temperature in TEMPERATURE_GRID:
        nll = _nll_from_logits(values, labels, float(temperature))
        if nll < best_nll:
            best_nll = nll
            best_temperature = float(temperature)
    return best_temperature


class AnomalyModel:
    """Minimum class-conditional squared Mahalanobis distance, not accident risk.

    On train rows, S uses the sample covariance denominator max(n_class-1, 1).
    Covariance is (1-shrinkage)*S + shrinkage*mean(diag(S))*I + ridge*I,
    where ridge=max(1e-6, mean(diag(S))*1e-6). This makes constant/missing-mask
    columns and one-row classes invertible. The input includes preprocessing's
    missing indicators. ``score`` returns shape (N,), with larger values meaning
    farther from every fitted synthetic path class.
    """

    def __init__(self):
        self.input_dim = None

    def fit(self, X, y, n_classes=3, shrinkage=0.2):
        values = _matrix(X, allow_empty=False)
        n_classes = _integer(n_classes, "n_classes", 2)
        shrinkage = _number(shrinkage, "shrinkage", minimum=0)
        if shrinkage > 1:
            raise ValueError("shrinkage must be in [0, 1]")
        mask, labels = _valid_labels(y, values.shape[0], n_classes)
        values = values[mask]
        n_features = values.shape[1]
        means, covariances, precisions, counts = [], [], [], []
        identity = np.eye(n_features)
        for label in range(n_classes):
            group = values[labels == label]
            if group.shape[0] == 0:
                raise ValueError("each class requires at least one training row")
            with np.errstate(over="ignore", invalid="ignore"):
                mean = group.mean(axis=0)
                centered = group - mean
                empirical = centered.T @ centered / max(group.shape[0] - 1, 1)
                variance = float(np.trace(empirical) / n_features)
                ridge = max(1e-6, variance * 1e-6)
                covariance = (1 - shrinkage) * empirical + (shrinkage * variance + ridge) * identity
            if not np.isfinite(mean).all() or not np.isfinite(covariance).all():
                raise ValueError("anomaly statistics overflowed")
            try:
                precision = np.linalg.inv(covariance)
            except np.linalg.LinAlgError as exc:
                raise ValueError("anomaly covariance is not invertible") from exc
            if not np.isfinite(precision).all():
                raise ValueError("anomaly precision is nonfinite")
            means.append(mean)
            covariances.append(covariance)
            precisions.append(precision)
            counts.append(group.shape[0])
        self.input_dim = n_features
        self.n_classes = n_classes
        self.shrinkage = shrinkage
        self.means_ = np.asarray(means)
        self.covariances_ = np.asarray(covariances)
        self.precisions_ = np.asarray(precisions)
        self.class_counts_ = np.asarray(counts, dtype=np.int64)
        return self

    def score(self, X):
        if self.input_dim is None:
            raise ValueError("anomaly model must be fitted before score")
        values = _matrix(X, n_features=self.input_dim)
        if values.shape[0] == 0:
            return np.empty(0, dtype=np.float64)
        distances = []
        with np.errstate(over="ignore", invalid="ignore"):
            for mean, precision in zip(self.means_, self.precisions_):
                difference = values - mean
                distances.append(np.einsum("ni,ij,nj->n", difference, precision, difference))
        scores = np.maximum(np.min(distances, axis=0), 0.0)
        if not np.isfinite(scores).all():
            raise ValueError("anomaly score overflowed")
        return scores

    def to_dict(self):
        if self.input_dim is None:
            raise ValueError("anomaly model must be fitted before serialization")
        return {
            "type": "anomaly", "schema_version": STATE_VERSION,
            "input_dim": self.input_dim, "n_classes": self.n_classes,
            "shrinkage": self.shrinkage, "means": self.means_.tolist(),
            "covariances": self.covariances_.tolist(),
            "class_counts": self.class_counts_.tolist(),
            "score_definition": "minimum_class_squared_mahalanobis",
        }

    @classmethod
    def from_dict(cls, state):
        state = _state(state, "anomaly")
        n_features = _integer(_required(state, "input_dim"), "input_dim", 1)
        n_classes = _integer(_required(state, "n_classes"), "n_classes", 2)
        shrinkage = _number(_required(state, "shrinkage"), "shrinkage", minimum=0)
        if shrinkage > 1 or state.get("score_definition") != "minimum_class_squared_mahalanobis":
            raise ValueError("invalid anomaly shrinkage or score definition")
        means = _array(state, "means", (n_classes, n_features))
        covariances = _array(state, "covariances", (n_classes, n_features, n_features))
        counts = _required(state, "class_counts")
        if not isinstance(counts, list) or len(counts) != n_classes:
            raise ValueError("class_counts must have n_classes entries")
        counts = [_integer(count, "class count", 1) for count in counts]
        precisions = []
        for covariance in covariances:
            if not np.allclose(covariance, covariance.T, rtol=0, atol=1e-10):
                raise ValueError("anomaly covariance must be symmetric")
            try:
                np.linalg.cholesky(covariance)
                precision = np.linalg.inv(covariance)
            except np.linalg.LinAlgError as exc:
                raise ValueError("anomaly covariance must be positive definite") from exc
            if not np.isfinite(precision).all():
                raise ValueError("anomaly precision is nonfinite")
            precisions.append(precision)
        result = cls()
        result.input_dim = n_features
        result.n_classes = n_classes
        result.shrinkage = shrinkage
        result.means_ = means
        result.covariances_ = covariances
        result.precisions_ = np.asarray(precisions)
        result.class_counts_ = np.asarray(counts, dtype=np.int64)
        return result
