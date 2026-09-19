import html
import json
import re
import time

import pydeck as pdk
import streamlit as st
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from src.agent import OrbitAssistAgent
from src.llm import create_llm
from src.tools import (
    estimate_delivery_quote,
    get_shipment_map_data,
    search_knowledge_base,
    track_shipment,
)


st.set_page_config(
    page_title="OrbitX Logistics",
    page_icon="📦",
    layout="wide",
)


def render_html(content):
    st.html(
        content.strip()
    )


def safe(value):
    return html.escape(
        str(value)
    )


def format_message(content):
    content = html.escape(
        str(content)
    )

    content = re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        content,
    )

    content = content.replace(
        "\n",
        "<br>"
    )

    return content


def build_chat_message(
    role,
    content,
):
    content = format_message(
        content
    )

    if role == "user":

        return f"""
        <div class="message-row user-row">

            <div class="message-group user-group">

                <div class="message-label user-label">
                    You
                </div>

                <div class="user-message">
                    {content}
                </div>

            </div>

        </div>
        """

    return f"""
    <div class="message-row assistant-row">

        <div class="message-group assistant-group">

            <div class="message-label assistant-label">

                <span class="assistant-mini-mark">
                    →
                </span>

                OrbitAssist

            </div>

            <div class="assistant-message">
                {content}
            </div>

        </div>

    </div>
    """


def build_thinking_message():
    return """
    <div class="message-row assistant-row">

        <div class="message-group assistant-group">

            <div class="message-label assistant-label">

                <span class="assistant-mini-mark">
                    →
                </span>

                OrbitAssist

            </div>

            <div class="assistant-message thinking-bubble">

                <span class="thinking-copy">
                    Generating response
                </span>

                <span class="thinking-dots">

                    <span></span>
                    <span></span>
                    <span></span>

                </span>

            </div>

        </div>

    </div>
    """


def build_chat_transcript(
    messages,
    show_thinking=False,
):
    items = [
        build_chat_message(
            message["role"],
            message["content"],
        )
        for message in messages
    ]

    if show_thinking:
        items.append(
            build_thinking_message()
        )

    items.reverse()

    content = "".join(
        items
    )

    return f"""
    <div class="chat-transcript">
        {content}
    </div>
    """


def choose_prompt(prompt):
    st.session_state.pending_prompt = (
        prompt
    )

    st.session_state.show_suggestions = (
        False
    )


def get_policy_answer(query):
    context = (
        search_knowledge_base.invoke(
            {
                "query": query
            }
        )
    )

    pages = sorted(
        set(
            re.findall(
                r"\[Source: page (\d+)\]",
                context,
            )
        )
    )

    llm = create_llm()

    messages = [
        SystemMessage(
            content=(
                "You are the OrbitX Policy Center. "
                "Answer only from the provided OrbitX "
                "knowledge-base context. "
                "Do not invent missing information. "
                "Give a clear and concise answer. "
                "Use short sections or bullet points when useful."
            )
        ),
        HumanMessage(
            content=(
                f"Question:\n{query}\n\n"
                f"Knowledge base context:\n{context}"
            )
        ),
    ]

    response = llm.invoke(
        messages
    )

    return response.content, pages


def get_progress(status):
    progress = {
        "Shipment Created": 0,
        "Pickup Scheduled": 0,
        "Picked Up": 1,
        "At Origin Hub": 1,
        "In Transit": 2,
        "At Destination Hub": 2,
        "Out for Delivery": 3,
        "Delivered": 4,
    }

    return progress.get(
        status,
        2,
    )


def render_timeline(status):
    steps = [
        "Created",
        "Picked up",
        "In transit",
        "Out for delivery",
        "Delivered",
    ]

    current = get_progress(
        status
    )

    items = []

    for index, step in enumerate(
        steps
    ):

        if index < current:
            state = "done"

        elif index == current:
            state = "active"

        else:
            state = "future"

        items.append(
            f"""
            <div class="timeline-step {state}">

                <div class="timeline-dot"></div>

                <div class="timeline-label">
                    {step}
                </div>

            </div>
            """
        )

    render_html(
        f"""
        <div class="timeline">
            {''.join(items)}
        </div>
        """
    )


def render_metric(
    label,
    value,
):
    render_html(
        f"""
        <div class="metric-card">

            <div class="metric-label">
                {safe(label)}
            </div>

            <div class="metric-value">
                {safe(value)}
            </div>

        </div>
        """
    )


def render_route_map(
    map_data,
):
    points = map_data[
        "points"
    ]

    route_path = map_data[
        "route_path"
    ]

    coordinates = [
        point["coordinates"]
        for point in points
    ]

    current_point = next(
        (
            point
            for point in points
            if point["name"]
            == "Latest recorded location"
        ),
        None,
    )

    completed_path = route_path
    remaining_path = []

    if (
        current_point
        and route_path
    ):

        current_coordinates = (
            current_point[
                "coordinates"
            ]
        )

        nearest_index = min(
            range(
                len(route_path)
            ),
            key=lambda index: (
                (
                    route_path[index][0]
                    - current_coordinates[0]
                ) ** 2
                +
                (
                    route_path[index][1]
                    - current_coordinates[1]
                ) ** 2
            ),
        )

        completed_path = (
            route_path[
                :nearest_index + 1
            ]
        )

        remaining_path = (
            route_path[
                nearest_index:
            ]
        )

        if completed_path:

            completed_path = (
                completed_path
                + [
                    current_coordinates
                ]
            )

        if remaining_path:

            remaining_path = (
                [
                    current_coordinates
                ]
                + remaining_path
            )

    center_lon = sum(
        coordinate[0]
        for coordinate in coordinates
    ) / len(coordinates)

    center_lat = sum(
        coordinate[1]
        for coordinate in coordinates
    ) / len(coordinates)

    longitude_span = (
        max(
            coordinate[0]
            for coordinate in coordinates
        )
        - min(
            coordinate[0]
            for coordinate in coordinates
        )
    )

    latitude_span = (
        max(
            coordinate[1]
            for coordinate in coordinates
        )
        - min(
            coordinate[1]
            for coordinate in coordinates
        )
    )

    span = max(
        longitude_span,
        latitude_span,
    )

    if span < 0.05:
        zoom = 11

    elif span < 0.2:
        zoom = 9

    elif span < 0.7:
        zoom = 7

    elif span < 2:
        zoom = 6

    else:
        zoom = 5

    layers = []

    if remaining_path:

        layers.append(
            pdk.Layer(
                "PathLayer",
                data=[
                    {
                        "path":
                            remaining_path
                    }
                ],
                get_path="path",
                get_color=[
                    191,
                    219,
                    254,
                ],
                get_width=5,
                width_min_pixels=3,
            )
        )

    if completed_path:

        layers.append(
            pdk.Layer(
                "PathLayer",
                data=[
                    {
                        "path":
                            completed_path
                    }
                ],
                get_path="path",
                get_color=[
                    37,
                    99,
                    235,
                ],
                get_width=6,
                width_min_pixels=4,
            )
        )

    normal_points = [
        point
        for point in points
        if point["name"]
        != "Latest recorded location"
    ]

    current_points = [
        point
        for point in points
        if point["name"]
        == "Latest recorded location"
    ]

    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=normal_points,
            get_position="coordinates",
            get_fill_color="color",
            get_radius=320,
            radius_min_pixels=8,
            radius_max_pixels=12,
            pickable=True,
        )
    )

    if current_points:

        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=current_points,
                get_position="coordinates",
                get_fill_color=[
                    14,
                    165,
                    233,
                ],
                get_line_color=[
                    255,
                    255,
                    255,
                ],
                stroked=True,
                line_width_min_pixels=3,
                get_radius=500,
                radius_min_pixels=11,
                radius_max_pixels=16,
                pickable=True,
            )
        )

        layers.append(
            pdk.Layer(
                "TextLayer",
                data=[
                    {
                        "position":
                            current_points[0][
                                "coordinates"
                            ],
                        "text":
                            "Latest scan",
                    }
                ],
                get_position="position",
                get_text="text",
                get_size=13,
                get_color=[
                    15,
                    23,
                    42,
                ],
                get_pixel_offset=[
                    0,
                    -25,
                ],
                get_text_anchor="'middle'",
                get_alignment_baseline="'bottom'",
            )
        )

    render_html(
        """
        <div class="map-legend">

            <div class="legend-item">
                <span class="legend-dot origin-dot"></span>
                Origin
            </div>

            <div class="legend-item">
                <span class="legend-dot current-dot"></span>
                Latest location
            </div>

            <div class="legend-item">
                <span class="legend-dot destination-dot"></span>
                Destination
            </div>

            <div class="legend-divider"></div>

            <div class="legend-item">
                <span class="route-line travelled-line"></span>
                Travelled
            </div>

            <div class="legend-item">
                <span class="route-line remaining-line"></span>
                Remaining
            </div>

        </div>
        """
    )

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            longitude=center_lon,
            latitude=center_lat,
            zoom=zoom,
            pitch=0,
        ),
        map_style=(
            "https://basemaps.cartocdn.com/"
            "gl/positron-gl-style/style.json"
        ),
        tooltip={
            "html": (
                "<b>{name}</b><br>"
                "{location}"
            ),
            "style": {
                "backgroundColor":
                    "#0F172A",
                "color":
                    "#FFFFFF",
            },
        },
    )

    st.pydeck_chart(
        deck,
        use_container_width=True,
    )


render_html(
    """
    <style>

    header[data-testid="stHeader"] {
        background: transparent;
    }

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    .stApp {
        background: #F6F8FC;
        color: #0F172A;
    }

    .block-container {
        max-width: 1180px;
        padding-top: 1.7rem;
        padding-bottom: 3rem;
    }

    .stMarkdown p,
    .stMarkdown li {
        color: #334155;
    }

    label,
    div[data-testid="stWidgetLabel"] p {
        color: #334155 !important;
    }

    input,
    textarea {
        color: #0F172A !important;
        background: #FFFFFF !important;
    }

    input::placeholder,
    textarea::placeholder {
        color: #94A3B8 !important;
        opacity: 1 !important;
    }

    div[data-baseweb="input"],
    div[data-baseweb="textarea"],
    div[data-baseweb="select"] > div {
        background: #FFFFFF !important;
        color: #0F172A !important;
    }

    div[data-baseweb="select"] span {
        color: #0F172A !important;
    }

    div[data-testid="stNumberInput"] input {
        color: #0F172A !important;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        background: #FFFFFF !important;
        color: #0F172A !important;
        border: 1px solid #DCE3ED !important;
        border-radius: 12px !important;
        min-height: 44px;
        font-weight: 650;
        box-shadow: none !important;
        transition: 0.15s ease;
    }

    div[data-testid="stButton"] button *,
    div[data-testid="stFormSubmitButton"] button * {
        color: inherit !important;
    }

    div[data-testid="stButton"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        background: #F1F5F9 !important;
        color: #0F172A !important;
        border-color: #CBD5E1 !important;
        transform: translateY(-1px);
    }

    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: #2563EB !important;
        color: #FFFFFF !important;
        border-color: #2563EB !important;
    }

    div[data-testid="stButton"] button[kind="primary"] *,
    div[data-testid="stFormSubmitButton"] button[kind="primary"] *,
    button[data-testid="stBaseButton-primary"] * {
        color: #FFFFFF !important;
    }

    .brand-row {
        display: flex;
        align-items: center;
        gap: 17px;
        margin-bottom: 28px;
    }

    .brand-mark {
        position: relative;
        width: 64px;
        height: 64px;
        flex: 0 0 64px;
        border-radius: 18px;
        background: #0F172A;
        box-shadow:
            0 10px 24px
            rgba(15, 23, 42, 0.15);
        overflow: hidden;
    }

    .parcel-icon {
        position: absolute;
        width: 27px;
        height: 29px;
        left: 10px;
        top: 17px;
        border: 2.5px solid #FFFFFF;
        border-radius: 4px;
        box-sizing: border-box;
    }

    .parcel-icon::before {
        content: "";
        position: absolute;
        left: -2.5px;
        top: 8px;
        width: 27px;
        border-top:
            2px solid
            rgba(255,255,255,0.75);
    }

    .parcel-tape {
        position: absolute;
        width: 7px;
        height: 10px;
        top: -2.5px;
        left: 7px;
        background: #2563EB;
        border-radius: 0 0 2px 2px;
    }

    .speed-line {
        position: absolute;
        height: 3px;
        border-radius: 999px;
        background: #60A5FA;
        right: 9px;
    }

    .speed-line-one {
        width: 17px;
        top: 24px;
    }

    .speed-line-two {
        width: 13px;
        top: 31px;
    }

    .speed-line-three {
        width: 9px;
        top: 38px;
    }

    .brand-name {
        color: #0F172A;
        font-size: 34px;
        font-weight: 850;
        letter-spacing: -1.3px;
        line-height: 1;
    }

    .brand-tagline {
        color: #64748B;
        font-size: 12px;
        margin-top: 8px;
    }

    .hero {
        position: relative;
        overflow: hidden;
        background: #0F172A;
        border-radius: 24px;
        padding: 33px 35px;
        margin-bottom: 27px;
    }

    .hero::after {
        content: "";
        position: absolute;
        width: 300px;
        height: 300px;
        right: -120px;
        top: -170px;
        border-radius: 50%;
        border:
            48px solid
            rgba(37,99,235,0.18);
    }

    .hero-eyebrow {
        color: #60A5FA;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        margin-bottom: 9px;
    }

    .hero-title {
        color: #FFFFFF;
        font-size: 32px;
        font-weight: 780;
        letter-spacing: -0.6px;
        line-height: 1.2;
        max-width: 700px;
    }

    .hero-copy {
        color: #CBD5E1;
        font-size: 14px;
        line-height: 1.65;
        max-width: 650px;
        margin-top: 11px;
    }

    .hero-features {
        display: flex;
        gap: 9px;
        flex-wrap: wrap;
        margin-top: 21px;
    }

    .hero-chip {
        color: #E2E8F0;
        font-size: 11px;
        border:
            1px solid
            rgba(255,255,255,0.12);
        background:
            rgba(255,255,255,0.06);
        padding: 7px 11px;
        border-radius: 999px;
    }

    div[data-baseweb="tab-list"] {
        display: flex;
        gap: 5px;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        padding: 5px;
        border-radius: 14px;
        margin-bottom: 25px;
    }

    button[data-baseweb="tab"] {
        flex: 1;
        border-radius: 10px;
        color: #64748B !important;
        font-weight: 650;
        height: 44px;
    }

    button[data-baseweb="tab"] * {
        color: inherit !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        background: #0F172A !important;
        color: #FFFFFF !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] * {
        color: #FFFFFF !important;
    }

    button[data-baseweb="tab"]:hover {
        background: #F1F5F9 !important;
        color: #0F172A !important;
    }

    button[data-baseweb="tab"][aria-selected="true"]:hover {
        background: #0F172A !important;
        color: #FFFFFF !important;
    }

    .section-title {
        color: #0F172A;
        font-size: 23px;
        font-weight: 760;
        letter-spacing: -0.4px;
    }

    .section-copy {
        color: #64748B;
        font-size: 13px;
        margin-top: 5px;
        margin-bottom: 20px;
    }

    .online-pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        color: #166534;
        background: #F0FDF4;
        border: 1px solid #DCFCE7;
        padding: 7px 11px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
    }

    .online-dot {
        width: 7px;
        height: 7px;
        background: #22C55E;
        border-radius: 50%;
    }

    .welcome-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        padding: 21px 23px;
        margin-bottom: 14px;
    }

    .welcome-title {
        color: #0F172A;
        font-size: 18px;
        font-weight: 750;
        margin-bottom: 7px;
    }

    .welcome-copy {
        color: #64748B;
        font-size: 13px;
        line-height: 1.6;
        max-width: 700px;
    }

    .quick-actions-title {
        color: #64748B;
        font-size: 11px;
        font-weight: 700;
        margin: 4px 0 8px 1px;
    }

    .chat-transcript {
        width: 100%;
        max-height: 390px;
        min-height: 0;
        overflow-y: auto;
        padding: 8px 10px 8px 4px;
        margin-top: 4px;
        margin-bottom: 8px;
        display: flex;
        flex-direction: column-reverse;
        scroll-behavior: smooth;
    }

    .chat-transcript::-webkit-scrollbar {
        width: 5px;
    }

    .chat-transcript::-webkit-scrollbar-track {
        background: transparent;
    }

    .chat-transcript::-webkit-scrollbar-thumb {
        background: #CBD5E1;
        border-radius: 999px;
    }

    .message-row {
        display: flex;
        width: 100%;
        flex: 0 0 auto;
        margin: 0 0 18px 0;
    }

    .message-row:first-child {
        margin-bottom: 4px;
    }

    .user-row {
        justify-content: flex-end;
    }

    .assistant-row {
        justify-content: flex-start;
    }

    .message-group {
        max-width: 72%;
    }

    .user-group {
        text-align: right;
    }

    .assistant-group {
        text-align: left;
    }

    .message-label {
        font-size: 10px;
        font-weight: 750;
        margin-bottom: 5px;
    }

    .user-label {
        color: #64748B;
        padding-right: 4px;
    }

    .assistant-label {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #2563EB;
        padding-left: 3px;
    }

    .assistant-mini-mark {
        width: 20px;
        height: 20px;
        border-radius: 7px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #0F172A;
        color: #60A5FA;
        font-size: 11px;
        font-weight: 800;
    }

    .user-message {
        display: inline-block;
        text-align: left;
        background: #2563EB;
        color: #FFFFFF;
        padding: 12px 15px;
        border-radius:
            17px 17px 5px 17px;
        font-size: 14px;
        line-height: 1.5;
        box-shadow:
            0 4px 12px
            rgba(37,99,235,0.12);
    }

    .user-message strong {
        color: #FFFFFF;
    }

    .assistant-message {
        display: inline-block;
        text-align: left;
        background: #FFFFFF;
        color: #1E293B;
        border: 1px solid #E2E8F0;
        padding: 12px 15px;
        border-radius:
            17px 17px 17px 5px;
        font-size: 14px;
        line-height: 1.5;
        box-shadow:
            0 3px 9px
            rgba(15,23,42,0.04);
    }

    .assistant-message strong {
        color: #0F172A;
    }

    .thinking-bubble {
        display: inline-flex;
        align-items: center;
        gap: 9px;
        min-width: 155px;
        color: #64748B;
    }

    .thinking-copy {
        color: #64748B;
        font-size: 12px;
        font-weight: 600;
    }

    .thinking-dots {
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }

    .thinking-dots span {
        display: block;
        width: 6px;
        height: 6px;
        background: #2563EB;
        border-radius: 50%;
        animation:
            orbitTyping
            1.15s
            infinite ease-in-out;
    }

    .thinking-dots span:nth-child(2) {
        animation-delay: 0.15s;
    }

    .thinking-dots span:nth-child(3) {
        animation-delay: 0.30s;
    }

    @keyframes orbitTyping {

        0%,
        70%,
        100% {
            opacity: 0.25;
            transform: translateY(0);
        }

        35% {
            opacity: 1;
            transform: translateY(-4px);
        }
    }

    div[data-testid="stChatInput"] {
        margin-top: 6px;
        background: #F6F8FC;
        padding: 4px 0 7px 0;
    }

    div[data-testid="stChatInput"] > div {
        background: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 16px !important;
        box-shadow:
            0 6px 20px
            rgba(15,23,42,0.07);
    }

    .shipment-head {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 19px;
        padding: 23px 24px;
        margin: 15px 0;
    }

    .status-badge {
        display: inline-block;
        background: #EFF6FF;
        color: #1D4ED8;
        border: 1px solid #DBEAFE;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 800;
        padding: 6px 10px;
        margin-bottom: 12px;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }

    .shipment-id {
        color: #0F172A;
        font-size: 25px;
        font-weight: 780;
    }

    .shipment-route {
        color: #64748B;
        font-size: 13px;
        margin-top: 6px;
    }

    .metric-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 15px;
        padding: 17px;
        min-height: 100px;
    }

    .metric-label {
        color: #64748B;
        font-size: 11px;
        font-weight: 650;
        margin-bottom: 8px;
    }

    .metric-value {
        color: #0F172A;
        font-size: 16px;
        font-weight: 750;
        line-height: 1.3;
    }

    .subsection-title {
        color: #0F172A;
        font-size: 16px;
        font-weight: 720;
        margin: 23px 0 11px 0;
    }

    .timeline {
        display: flex;
        width: 100%;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 17px;
        padding: 22px 16px 18px;
        margin-bottom: 15px;
    }

    .timeline-step {
        flex: 1;
        position: relative;
        text-align: center;
    }

    .timeline-step::before {
        content: "";
        position: absolute;
        height: 3px;
        background: #E2E8F0;
        top: 7px;
        left: 0;
        width: 100%;
        z-index: 0;
    }

    .timeline-step:first-child::before {
        left: 50%;
        width: 50%;
    }

    .timeline-step:last-child::before {
        width: 50%;
    }

    .timeline-dot {
        position: relative;
        z-index: 2;
        width: 16px;
        height: 16px;
        margin: 0 auto 10px;
        border-radius: 50%;
        border: 3px solid #CBD5E1;
        background: #FFFFFF;
    }

    .timeline-step.done::before,
    .timeline-step.active::before {
        background: #2563EB;
    }

    .timeline-step.done .timeline-dot {
        border-color: #2563EB;
        background: #2563EB;
    }

    .timeline-step.active .timeline-dot {
        border-color: #2563EB;
        background: #FFFFFF;
        box-shadow:
            0 0 0 5px
            #DBEAFE;
    }

    .timeline-label {
        color: #64748B;
        font-size: 10px;
        font-weight: 650;
    }

    .timeline-step.active .timeline-label {
        color: #1D4ED8;
        font-weight: 800;
    }

    .map-note {
        color: #64748B;
        font-size: 11px;
        margin-bottom: 9px;
    }

    .map-legend {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 14px;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 13px;
        padding: 11px 14px;
        margin-bottom: 10px;
    }

    .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #475569;
        font-size: 11px;
        font-weight: 650;
    }

    .legend-dot {
        display: inline-block;
        width: 9px;
        height: 9px;
        border-radius: 50%;
    }

    .origin-dot {
        background: #0F172A;
    }

    .current-dot {
        background: #0EA5E9;
        box-shadow:
            0 0 0 3px
            #E0F2FE;
    }

    .destination-dot {
        background: #2563EB;
    }

    .legend-divider {
        height: 18px;
        width: 1px;
        background: #E2E8F0;
    }

    .route-line {
        display: inline-block;
        width: 20px;
        height: 3px;
        border-radius: 999px;
    }

    .travelled-line {
        background: #2563EB;
    }

    .remaining-line {
        background: #BFDBFE;
    }

    .activity-card {
        display: flex;
        gap: 14px;
        align-items: flex-start;
        background: #0F172A;
        border-radius: 17px;
        padding: 20px;
        margin-top: 13px;
    }

    .activity-icon {
        width: 36px;
        height: 36px;
        flex: 0 0 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 11px;
        background: #2563EB;
        color: #FFFFFF;
        font-size: 17px;
    }

    .activity-label {
        color: #93C5FD;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.7px;
    }

    .activity-text {
        color: #FFFFFF;
        font-size: 15px;
        font-weight: 650;
        margin-top: 4px;
    }

    .activity-time {
        color: #94A3B8;
        font-size: 11px;
        margin-top: 7px;
    }

    .quote-hero {
        background: #0F172A;
        border-radius: 20px;
        padding: 25px;
        margin: 18px 0 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
    }

    .quote-route {
        color: #CBD5E1;
        font-size: 13px;
    }

    .quote-service {
        display: inline-block;
        color: #BFDBFE;
        background:
            rgba(37,99,235,0.18);
        border:
            1px solid
            rgba(96,165,250,0.25);
        border-radius: 999px;
        padding: 5px 9px;
        font-size: 10px;
        font-weight: 800;
        margin-bottom: 9px;
        text-transform: uppercase;
    }

    .quote-total-label {
        color: #94A3B8;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        text-align: right;
    }

    .quote-total {
        color: #FFFFFF;
        font-size: 31px;
        font-weight: 800;
        margin-top: 4px;
        white-space: nowrap;
    }

    .breakdown-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 17px;
        padding: 21px;
        margin-top: 14px;
    }

    .breakdown-title {
        color: #0F172A;
        font-size: 15px;
        font-weight: 730;
        margin-bottom: 13px;
    }

    .breakdown-row {
        display: flex;
        justify-content: space-between;
        padding: 9px 0;
        border-bottom:
            1px solid
            #F1F5F9;
        color: #64748B;
        font-size: 13px;
    }

    .breakdown-row span:last-child {
        color: #0F172A;
        font-weight: 700;
    }

    .breakdown-total {
        display: flex;
        justify-content: space-between;
        padding-top: 14px;
        margin-top: 3px;
        border-top:
            1px solid
            #CBD5E1;
        color: #0F172A;
        font-size: 15px;
        font-weight: 800;
    }

    .recommendation-card {
        background: #FFF7ED;
        border: 1px solid #FED7AA;
        border-radius: 16px;
        padding: 20px;
        margin-top: 15px;
    }

    .recommendation-title {
        color: #9A3412;
        font-size: 15px;
        font-weight: 750;
    }

    .recommendation-copy {
        color: #7C2D12;
        font-size: 13px;
        margin-top: 6px;
    }

    .policy-result-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 15px;
        margin-bottom: 12px;
    }

    .policy-label {
        color: #2563EB;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    .policy-status {
        color: #166534;
        background: #F0FDF4;
        border: 1px solid #DCFCE7;
        padding: 5px 9px;
        border-radius: 999px;
        font-size: 10px;
        font-weight: 700;
    }

    .source-pill {
        display: inline-block;
        color: #475569;
        background: #F1F5F9;
        border-radius: 999px;
        padding: 5px 9px;
        font-size: 10px;
        font-weight: 650;
        margin-right: 5px;
        margin-top: 9px;
    }

    .footer-copy {
        text-align: center;
        color: #94A3B8;
        font-size: 11px;
        margin-top: 45px;
    }

    @media (max-width: 760px) {

        .brand-name {
            font-size: 27px;
        }

        .brand-mark {
            width: 56px;
            height: 56px;
            flex-basis: 56px;
        }

        .hero {
            padding: 25px;
        }

        .hero-title {
            font-size: 26px;
        }

        .message-group {
            max-width: 88%;
        }

        .quote-hero {
            display: block;
        }

        .quote-total-label,
        .quote-total {
            text-align: left;
        }

        .quote-total {
            margin-top: 6px;
        }

        .timeline-label {
            font-size: 8px;
        }

        .legend-divider {
            display: none;
        }
    }

    </style>
    """
)


if "agent" not in st.session_state:
    st.session_state.agent = (
        OrbitAssistAgent()
    )


if "messages" not in st.session_state:
    st.session_state.messages = []


if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None


if "show_suggestions" not in st.session_state:
    st.session_state.show_suggestions = True


if "tracking_result" not in st.session_state:
    st.session_state.tracking_result = None


if "tracking_map" not in st.session_state:
    st.session_state.tracking_map = None


if "quote_result" not in st.session_state:
    st.session_state.quote_result = None


if "policy_answer" not in st.session_state:
    st.session_state.policy_answer = None


if "policy_pages" not in st.session_state:
    st.session_state.policy_pages = []


render_html(
    """
    <div class="brand-row">

        <div class="brand-mark">

            <div class="parcel-icon">
                <span class="parcel-tape"></span>
            </div>

            <span class="speed-line speed-line-one"></span>
            <span class="speed-line speed-line-two"></span>
            <span class="speed-line speed-line-three"></span>

        </div>

        <div>

            <div class="brand-name">
                OrbitX Logistics
            </div>

            <div class="brand-tagline">
                Intelligent logistics support
            </div>

        </div>

    </div>
    """
)


render_html(
    """
    <div class="hero">

        <div class="hero-eyebrow">
            OrbitAssist AI
        </div>

        <div class="hero-title">
            Everything your shipment needs,
            in one place.
        </div>

        <div class="hero-copy">
            Track deliveries, calculate live route-based
            quotes and find the right OrbitX policy
            without waiting for support.
        </div>

        <div class="hero-features">

            <span class="hero-chip">
                24/7 AI support
            </span>

            <span class="hero-chip">
                Route-based estimates
            </span>

            <span class="hero-chip">
                Shipment tracking
            </span>

            <span class="hero-chip">
                Smart policy search
            </span>

        </div>

    </div>
    """
)


assistant_tab, tracking_tab, quote_tab, policy_tab = st.tabs(
    [
        "AI Assistant",
        "Track Shipment",
        "Get a Quote",
        "Policy Center",
    ]
)


with assistant_tab:

    pending_from_button = (
        st.session_state.pending_prompt
    )

    if pending_from_button:
        st.session_state.pending_prompt = None
        st.session_state.show_suggestions = False


    title_col, status_col, button_col = st.columns(
        [
            5,
            1.5,
            1.2,
        ]
    )


    with title_col:

        render_html(
            """
            <div class="section-title">
                How can we help?
            </div>

            <div class="section-copy">
                Ask about a shipment, delivery estimate
                or OrbitX policy.
            </div>
            """
        )


    with status_col:

        render_html(
            """
            <div style="padding-top:5px;">

                <div class="online-pill">

                    <span class="online-dot"></span>

                    OrbitAssist online

                </div>

            </div>
            """
        )


    with button_col:

        if st.button(
            "New chat",
            key="new_chat",
            use_container_width=True,
        ):

            st.session_state.agent = (
                OrbitAssistAgent()
            )

            st.session_state.messages = []

            st.session_state.pending_prompt = None

            st.session_state.show_suggestions = True

            st.rerun()


    suggestions_area = st.empty()


    if (
        not st.session_state.messages
        and st.session_state.show_suggestions
        and pending_from_button is None
    ):

        with suggestions_area.container():

            render_html(
                """
                <div class="welcome-card">

                    <div class="welcome-title">
                        How can we help today?
                    </div>

                    <div class="welcome-copy">
                        Choose a common request or ask
                        OrbitAssist anything below.
                    </div>

                </div>

                <div class="quick-actions-title">
                    Quick actions
                </div>
                """
            )


            q1, q2, q3 = st.columns(
                3
            )


            with q1:

                st.button(
                    "Track a shipment",
                    key="quick_track",
                    use_container_width=True,
                    on_click=choose_prompt,
                    args=(
                        "I need help tracking a shipment.",
                    ),
                )


            with q2:

                st.button(
                    "Plan a delivery",
                    key="quick_quote",
                    use_container_width=True,
                    on_click=choose_prompt,
                    args=(
                        "I need help planning a delivery.",
                    ),
                )


            with q3:

                st.button(
                    "Ask about shipping",
                    key="quick_policy",
                    use_container_width=True,
                    on_click=choose_prompt,
                    args=(
                        "I have a question about shipping "
                        "with OrbitX.",
                    ),
                )


    chat_area = st.empty()


    if st.session_state.messages:

        chat_area.html(
            build_chat_transcript(
                st.session_state.messages
            ).strip()
        )


    typed_input = st.chat_input(
        "Message OrbitAssist..."
    )


    incoming_message = None


    if pending_from_button:

        incoming_message = (
            pending_from_button
        )

    elif typed_input:

        incoming_message = (
            typed_input
        )


    if incoming_message:

        suggestions_area.empty()

        st.session_state.show_suggestions = (
            False
        )

        st.session_state.messages.append(
            {
                "role": "user",
                "content":
                    incoming_message,
            }
        )


        chat_area.html(
            build_chat_transcript(
                st.session_state.messages,
                show_thinking=True,
            ).strip()
        )


        time.sleep(
            0.08
        )


        try:

            response = (
                st.session_state.agent.chat(
                    incoming_message
                )
            )

        except Exception:

            response = (
                "I couldn't complete that request "
                "right now. Please try again."
            )


        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
            }
        )


        chat_area.html(
            build_chat_transcript(
                st.session_state.messages
            ).strip()
        )


with tracking_tab:

    render_html(
        """
        <div class="section-title">
            Track your shipment
        </div>

        <div class="section-copy">
            Check the latest recorded shipment
            status and route.
        </div>
        """
    )

    tracking_col, track_col = st.columns(
        [
            5,
            1,
        ]
    )

    with tracking_col:

        tracking_id = st.text_input(
            "Tracking ID",
            placeholder=(
                "Enter tracking ID · OX10452"
            ),
            label_visibility="collapsed",
            key="tracking_input",
        )

    with track_col:

        track_button = st.button(
            "Track",
            key="track_button",
            type="primary",
            use_container_width=True,
        )


    if track_button:

        if not tracking_id.strip():

            st.warning(
                "Please enter a tracking ID."
            )

        else:

            with st.spinner(
                "Checking shipment..."
            ):

                result = (
                    track_shipment.invoke(
                        {
                            "tracking_id":
                                tracking_id
                        }
                    )
                )

            try:

                shipment = json.loads(
                    result
                )

            except json.JSONDecodeError:

                shipment = None


            if shipment:

                st.session_state.tracking_result = (
                    shipment
                )

                with st.spinner(
                    "Loading shipment route..."
                ):

                    st.session_state.tracking_map = (
                        get_shipment_map_data(
                            shipment[
                                "tracking_id"
                            ]
                        )
                    )

            else:

                st.session_state.tracking_result = None
                st.session_state.tracking_map = None

                st.error(
                    result
                )


    shipment = (
        st.session_state.tracking_result
    )


    if shipment:

        render_html(
            f"""
            <div class="shipment-head">

                <div class="status-badge">
                    {safe(shipment["status"])}
                </div>

                <div class="shipment-id">
                    {safe(shipment["tracking_id"])}
                </div>

                <div class="shipment-route">
                    {safe(shipment["origin"])}
                    &nbsp; → &nbsp;
                    {safe(shipment["destination"])}
                </div>

            </div>
            """
        )


        c1, c2, c3, c4 = st.columns(
            4
        )

        with c1:

            render_metric(
                "Service",
                shipment["service"],
            )

        with c2:

            render_metric(
                "Expected",
                shipment[
                    "expected_delivery"
                ],
            )

        with c3:

            render_metric(
                "Current location",
                shipment[
                    "current_location"
                ],
            )

        with c4:

            render_metric(
                "Attempts",
                shipment[
                    "delivery_attempts"
                ],
            )


        render_html(
            """
            <div class="subsection-title">
                Shipment journey
            </div>
            """
        )

        render_timeline(
            shipment["status"]
        )


        render_html(
            """
            <div class="subsection-title">
                Route overview
            </div>

            <div class="map-note">
                The latest location represents the most
                recent OrbitX scan, not real-time courier GPS.
            </div>
            """
        )


        map_data = (
            st.session_state.tracking_map
        )


        if map_data:

            render_route_map(
                map_data
            )

        else:

            st.info(
                "The route map is temporarily unavailable."
            )


        render_html(
            f"""
            <div class="activity-card">

                <div class="activity-icon">
                    ↗
                </div>

                <div>

                    <div class="activity-label">
                        Latest shipment activity
                    </div>

                    <div class="activity-text">
                        {safe(shipment["notes"])}
                    </div>

                    <div class="activity-time">
                        Updated
                        {safe(shipment["last_update"])}
                    </div>

                </div>

            </div>
            """
        )


with quote_tab:

    render_html(
        """
        <div class="section-title">
            Get a delivery quote
        </div>

        <div class="section-copy">
            Calculate a domestic OrbitX estimate
            using live road-distance data.
        </div>
        """
    )


    with st.form(
        "quote_form"
    ):

        col1, col2 = st.columns(
            2
        )

        with col1:

            origin = st.text_input(
                "Origin",
                placeholder="New Cairo",
            )

            weight = st.number_input(
                "Package weight (kg)",
                min_value=0.1,
                max_value=30.0,
                value=1.0,
                step=0.5,
            )

        with col2:

            destination = st.text_input(
                "Destination",
                placeholder="Alexandria",
            )

            service = st.selectbox(
                "Service",
                [
                    "Standard",
                    "Express",
                    "Same-Day",
                ],
            )


        insurance = st.checkbox(
            "Add shipment insurance"
        )

        declared_value = 0.0

        if insurance:

            declared_value = st.number_input(
                "Declared value (EGP)",
                min_value=1.0,
                max_value=50000.0,
                value=1000.0,
                step=100.0,
            )


        quote_button = (
            st.form_submit_button(
                "Calculate quote",
                type="primary",
                use_container_width=True,
            )
        )


    if quote_button:

        if (
            not origin.strip()
            or not destination.strip()
        ):

            st.warning(
                "Please enter both origin "
                "and destination."
            )

        else:

            with st.spinner(
                "Calculating route and price..."
            ):

                result = (
                    estimate_delivery_quote.invoke(
                        {
                            "origin":
                                origin,
                            "destination":
                                destination,
                            "weight_kg":
                                weight,
                            "service_type":
                                service,
                            "insurance":
                                insurance,
                            "declared_value":
                                declared_value,
                        }
                    )
                )

            try:

                quote = json.loads(
                    result
                )

                st.session_state.quote_result = (
                    quote
                )

            except json.JSONDecodeError:

                st.session_state.quote_result = None

                st.error(
                    result
                )


    quote = (
        st.session_state.quote_result
    )


    if quote:

        if not quote.get(
            "available",
            True,
        ):

            render_html(
                f"""
                <div class="recommendation-card">

                    <div class="recommendation-title">
                        Same-Day isn't available
                        for this route
                    </div>

                    <div class="recommendation-copy">

                        {safe(quote["reason"])}

                        <br><br>

                        Recommended service:

                        <strong>
                            {safe(
                                quote[
                                    "recommended_service"
                                ]
                            )}
                        </strong>

                    </div>

                </div>
                """
            )

        else:

            breakdown = quote[
                "price_breakdown"
            ]

            estimated_price = quote[
                "estimated_price"
            ]

            render_html(
                f"""
                <div class="quote-hero">

                    <div>

                        <div class="quote-service">
                            {safe(quote["service"])}
                        </div>

                        <div class="quote-route">
                            {safe(quote["origin"])}
                            &nbsp; → &nbsp;
                            {safe(quote["destination"])}
                        </div>

                    </div>

                    <div>

                        <div class="quote-total-label">
                            Estimated total
                        </div>

                        <div class="quote-total">
                            {estimated_price:,.2f}
                            EGP
                        </div>

                    </div>

                </div>
                """
            )


            c1, c2, c3 = st.columns(
                3
            )

            with c1:

                render_metric(
                    "Route distance",
                    (
                        f"{quote['distance_km']:,.1f} km"
                    ),
                )

            with c2:

                render_metric(
                    "Driving time",
                    (
                        f"{quote['estimated_drive_time_minutes']} min"
                    ),
                )

            with c3:

                render_metric(
                    "Package weight",
                    (
                        f"{quote['weight_kg']} kg"
                    ),
                )


            render_html(
                f"""
                <div class="breakdown-card">

                    <div class="breakdown-title">
                        Price breakdown
                    </div>

                    <div class="breakdown-row">

                        <span>
                            Base delivery fee
                        </span>

                        <span>
                            {breakdown["base_fee"]:,.2f}
                            EGP
                        </span>

                    </div>

                    <div class="breakdown-row">

                        <span>
                            Extra weight
                        </span>

                        <span>
                            {breakdown["extra_weight_fee"]:,.2f}
                            EGP
                        </span>

                    </div>

                    <div class="breakdown-row">

                        <span>
                            Distance charge
                        </span>

                        <span>
                            {breakdown["distance_fee"]:,.2f}
                            EGP
                        </span>

                    </div>

                    <div class="breakdown-row">

                        <span>
                            Insurance
                        </span>

                        <span>
                            {breakdown["insurance_fee"]:,.2f}
                            EGP
                        </span>

                    </div>

                    <div class="breakdown-total">

                        <span>
                            Estimated total
                        </span>

                        <span>
                            {estimated_price:,.2f}
                            EGP
                        </span>

                    </div>

                </div>
                """
            )


with policy_tab:

    render_html(
        """
        <div class="section-title">
            Policy Center
        </div>

        <div class="section-copy">
            Search the OrbitX knowledge base
            or explore common policy topics.
        </div>
        """
    )


    query_col, search_col = st.columns(
        [
            5,
            1,
        ]
    )

    with query_col:

        policy_query = st.text_input(
            "Policy search",
            placeholder=(
                "Ask about returns, insurance, "
                "damaged shipments..."
            ),
            label_visibility="collapsed",
            key="policy_search_input",
        )

    with search_col:

        policy_search = st.button(
            "Search",
            key="policy_search_button",
            type="primary",
            use_container_width=True,
        )


    policy_topics = {
        "Delivery services":
            "OrbitX delivery services and delivery times",

        "Shipping rates":
            "OrbitX domestic shipping rates and pricing rules",

        "Packaging & limits":
            "OrbitX packaging requirements and parcel limits",

        "Restricted items":
            "OrbitX prohibited and restricted shipping items",

        "Cash on delivery":
            "OrbitX cash on delivery policy",

        "Insurance":
            "OrbitX shipment insurance policy",

        "Tracking statuses":
            "OrbitX tracking statuses and what they mean",

        "Failed delivery":
            "OrbitX failed delivery attempt policy",

        "Returns":
            "OrbitX return to sender policy",

        "Lost shipments":
            "OrbitX lost shipment policy and compensation",

        "Damaged shipments":
            "OrbitX damaged shipment claims policy",

        "International shipping":
            "OrbitX international shipping and customs policy",
    }


    st.caption(
        "Popular topics"
    )


    topic1, topic2, topic3 = st.columns(
        3
    )

    selected_query = None


    with topic1:

        if st.button(
            "Insurance",
            key="policy_insurance",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Insurance"
                ]
            )

        if st.button(
            "Returns",
            key="policy_returns",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Returns"
                ]
            )


    with topic2:

        if st.button(
            "Failed delivery",
            key="policy_failed_delivery",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Failed delivery"
                ]
            )

        if st.button(
            "Packaging & limits",
            key="policy_packaging",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Packaging & limits"
                ]
            )


    with topic3:

        if st.button(
            "Lost shipments",
            key="policy_lost",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Lost shipments"
                ]
            )

        if st.button(
            "Restricted items",
            key="policy_restricted",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    "Restricted items"
                ]
            )


    st.write("")


    library_topic = st.selectbox(
        "Browse the full policy library",
        [
            "Select a policy topic"
        ]
        + list(
            policy_topics.keys()
        ),
    )


    if (
        library_topic
        != "Select a policy topic"
    ):

        if st.button(
            "Open policy",
            key="open_policy",
            use_container_width=True,
        ):

            selected_query = (
                policy_topics[
                    library_topic
                ]
            )


    if (
        policy_search
        and policy_query.strip()
    ):

        selected_query = (
            policy_query.strip()
        )


    if selected_query:

        with st.spinner(
            "Searching OrbitX policies..."
        ):

            answer, pages = (
                get_policy_answer(
                    selected_query
                )
            )

        st.session_state.policy_answer = (
            answer
        )

        st.session_state.policy_pages = (
            pages
        )


    if st.session_state.policy_answer:

        st.write("")

        with st.container(
            border=True
        ):

            render_html(
                """
                <div class="policy-result-header">

                    <div class="policy-label">
                        OrbitX Knowledge Base
                    </div>

                    <div class="policy-status">
                        Grounded answer
                    </div>

                </div>
                """
            )

            st.markdown(
                st.session_state.policy_answer
            )

            if st.session_state.policy_pages:

                page_html = "".join(
                    (
                        '<span class="source-pill">'
                        'Knowledge Base · page '
                        f'{safe(page)}'
                        '</span>'
                    )
                    for page
                    in st.session_state.policy_pages
                )

                render_html(
                    f"""
                    <div>
                        {page_html}
                    </div>
                    """
                )


render_html(
    """
    <div class="footer-copy">
        OrbitX Logistics · Powered by OrbitAssist
    </div>
    """
)