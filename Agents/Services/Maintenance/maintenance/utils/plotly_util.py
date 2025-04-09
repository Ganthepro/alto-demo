import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_plot(df: pd.DataFrame(), x: list, y: list, features: list, asset_name: str):
    """
    Render the plot for AC anomaly detection
    Args:
        df          : Dataframe of the data
        x           : timestamp of anomaly occurrence
        y           : optional anomaly data on Y-axis
        features    : features to be plotted
        asset_name  : name of the asset

    Returns:
        fig         : figure of the plot
    """

    # unit_map_path = "configs/unit_map.json"
    # unit_map = json.load(open(unit_map_path))
    unit_map = {
        "power": "kW",
        "current": "A",
        "voltage": "V",
        "energy": "kWh",
        "temperature": "°C",
        "humidity": "%RH",
        "time": "hrs",
        "diff_temp": "°C"
    }
    color = ['blue', 'black', 'brown', 'orange', 'purple', 'pink', 'gray', 'olive', 'cyan']
    fig = make_subplots(
        rows=len(features)+1,
        cols=1,
        vertical_spacing=0.1,
        subplot_titles=tuple(features),
        shared_xaxes=True
    )

    for idx, i in enumerate(features):

        fig.add_trace(
            go.Scatter(x=df.index, y=df[i], name=i + " " + f"({unit_map[i]})", line={'width': 3, 'color': f'{color[idx]}'}),
            row=idx+1,
            col=1
        )

        # Plot anomaly point on the last figure
        if idx == len(features)-1:
            fig.add_trace(
                go.Scatter(x=x, y=df[i].loc[x], name="Anomaly Detection", mode='markers', marker={'color': 'red', 'symbol':'x', 'size':10}),
                row=idx+1,
                col=1
            )
            fig.update_xaxes(title_text="Datetime", row=idx + 1, col=1)

        template = 'plotly_white'
        fig.update_layout(
            title=f"<b>Anomaly Detection on {asset_name}<b>"
        )

        fig.update_yaxes(title_text=f"{i} ({unit_map[i]})", row=idx+1, col=1)


    return fig