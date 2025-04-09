from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd

def dbscan_model(_df: pd.DataFrame, features: list, _eps: float, _min_samples: int):
    """
    DBSCAN model for anomaly detection
    Args:
        _df             : dataframe of data to be inferencing
        features        : features to be used for inference
        _eps            : value of radius of circle that cover the data point for clustering (0-1)
        _min_samples    : minimum number of sample surrouded to be consider as one cluster

    Returns:
        x               : list of timestamp of anomaly occurence
        y               : list of anomaly data on Y-axis

    """
    # Preprocessing with Standard Scaler
    scaler = StandardScaler()
    data = scaler.fit_transform(_df[features]) # Transformed array

    # Perform clustering algorithm
    clustering = DBSCAN(eps=_eps, min_samples=_min_samples).fit(data.reshape(-1, len(features)))

    # Get anomaly data
    labels = clustering.labels_
    outlier_pos = np.where(labels == -1)[0]

    # Save inference result in the list
    x = []
    y = []
    for pos in outlier_pos:
        y.append(np.array(_df[features])[pos])
        x.append(_df[features].index[pos])

    return x, y