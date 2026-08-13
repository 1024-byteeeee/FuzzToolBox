"""Semantic colors shared by QSS and custom-painted widgets."""

LIGHT = {
    "window": "#f5f7fa", "surface": "#ffffff", "surface_alt": "#fbfcfe",
    "surface_muted": "#f0f2f5", "text": "#303133", "text_secondary": "#606266",
    "text_muted": "#909399", "border": "#dcdfe6", "border_soft": "#e4e7ed",
    "primary": "#409eff", "primary_soft": "#ecf5ff", "primary_text": "#1677d2",
    "gutter": "#f2f5f9", "gutter_border": "#d8dee8", "current_line": "#e8f3ff",
    "error_bg": "#fde2e2", "error": "#d64545",
    "diff_remove_bg": "#f8d7da", "diff_remove_strong": "#f1b8b8",
    "diff_add_bg": "#d9f2df", "diff_add_strong": "#9edbb0",
    "diff_change_bg": "#fff0bf", "diff_info_bg": "#e8f1fb", "diff_context_bg": "#eef2f7",
    "syntax_keyword": "#7b3fb2", "syntax_string": "#16825d", "syntax_number": "#b15c00",
    "syntax_comment": "#718096", "syntax_type": "#087f8c", "syntax_tag": "#b43b52",
    "syntax_property": "#1769aa", "syntax_preprocessor": "#9a5b13",
}

DARK = {
    "window": "#111827", "surface": "#182230", "surface_alt": "#202b3a",
    "surface_muted": "#263244", "text": "#edf2f7", "text_secondary": "#c4cedb",
    "text_muted": "#93a4b8", "border": "#46556a", "border_soft": "#344154",
    "primary": "#62adff", "primary_soft": "#203b57", "primary_text": "#79bdff",
    "gutter": "#151e2b", "gutter_border": "#344154", "current_line": "#263f5c",
    "error_bg": "#4a252b", "error": "#ff7b83",
    "diff_remove_bg": "#482a31", "diff_remove_strong": "#63343c",
    "diff_add_bg": "#203f31", "diff_add_strong": "#2e5a42",
    "diff_change_bg": "#4a3d22", "diff_info_bg": "#233950", "diff_context_bg": "#263244",
    "syntax_keyword": "#c792ea", "syntax_string": "#7fdbca", "syntax_number": "#f6b26b",
    "syntax_comment": "#8c9bab", "syntax_type": "#63d5da", "syntax_tag": "#ff8fa3",
    "syntax_property": "#82bfff", "syntax_preprocessor": "#e8bc74",
}


# Exact replacements preserve the current visual hierarchy without requiring
# every historic QSS rule to be rewritten at once.
DARK_REPLACEMENTS = {
    "#f5f7fa": DARK["window"], "#ffffff": DARK["surface"], "#fbfcfe": DARK["surface_alt"],
    "#fafcff": DARK["surface_alt"], "#fafafa": DARK["surface_alt"], "#f8fafc": "#1d2938",
    "#f8fbff": "#1d2b3b", "#f4f9ff": "#1b3046", "#f0f2f5": DARK["surface_muted"],
    "#303133": DARK["text"], "#263445": "#e1e8f0", "#172b4d": DARK["text"],
    "#4e5969": DARK["text_secondary"], "#606266": DARK["text_secondary"],
    "#718096": DARK["text_muted"], "#909399": DARK["text_muted"], "#a8abb2": "#8292a6",
    "#dcdfe6": DARK["border"], "#e4e7ed": DARK["border_soft"], "#e4eaf1": DARK["border_soft"],
    "#ebeef5": "#2d394a", "#c0c4cc": "#5a687b", "#409eff": DARK["primary"],
    "#66b1ff": "#82beff", "#337ecc": "#418bd5", "#79bbff": "#86c4ff",
    "#1677d2": DARK["primary_text"], "#1769aa": "#72b7f4", "#145ca6": "#79bdff",
    "#ecf5ff": DARK["primary_soft"], "#d9ecff": "#294866", "#c6e2ff": "#315677",
    "#b3d8ff": "#3f668b", "#a8d3ff": "#47759f", "#e6f3ff": "#263f59",
    "#f0f8ff": "#20364d", "#406080": "#a9c4df", "#8ea1b2": "#8fa3b7",
    "#f0faf4": "#1b3025", "#e3f6ea": "#21402f",
    "#fef0f0": "#44252a", "#fde2e2": "#633139", "#c45656": "#ff858b",
    "#f0f9eb": "#203d2b", "#d9ecce": "#315b3e", "#2d7a46": "#72d596",
    "#fff8e6": "#46381f", "#f5d99a": "#725b2d", "#8a6116": "#f0c66d",
    "#e9fbfa": "#173f43", "#a9e8e4": "#34777a", "#176b87": "#1b708d",
    "#2a7d96": "#287f9c", "#bdecea": "#c8f3f1", "#c9f3f1": "#d5f8f6",
    "#e8ffff": "#efffff", "#b9dbff": "#41698f",
}
