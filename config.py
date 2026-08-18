"""
config.py
Cấu hình dùng chung: từ điển chuẩn hóa chỉ tiêu tài chính, alias công ty,
cấu hình cache, tỷ số tài chính và constants.
"""

import os

# ---------------------------------------------------------------------------
# Cache settings
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
CACHE_TTL_HOURS = 24

# ---------------------------------------------------------------------------
# Supported tickers with full Vietnamese names
# ---------------------------------------------------------------------------
SUPPORTED_TICKERS = {
    "VCB":  "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)",
    "BID":  "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam (BIDV)",
    "CTG":  "Ngân hàng TMCP Công Thương Việt Nam (VietinBank)",
    "VNM":  "Công ty CP Sữa Việt Nam (Vinamilk)",
    "FPT":  "Công ty CP FPT",
    "VIC":  "Tập đoàn Vingroup",
    "MSN":  "Tập đoàn Masan",
    "VJC":  "Hàng không Vietjet",
    "SAB":  "Tổng Công ty CP Bia – Rượu – NGK Sài Gòn (SABECO)",
    "HPG":  "Tập đoàn Hòa Phát",
    "MWG":  "Công ty CP Đầu tư Thế Giới Di Động",
    "VRE":  "Công ty CP Vincom Retail",
    "HDB":  "Ngân hàng TMCP Phát triển TP. Hồ Chí Minh (HDBank)",
    "TCB":  "Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)",
    "VPB":  "Ngân hàng TMCP Việt Nam Thịnh Vượng (VPBank)",
}

DEFAULT_SYMBOLS = list(SUPPORTED_TICKERS.keys())

# ---------------------------------------------------------------------------
# LINE_ITEM_PATTERNS: keyword mapping for financial line items
# ---------------------------------------------------------------------------
LINE_ITEM_PATTERNS = {
    # --- Kết quả kinh doanh ---
    "doanh_thu_thuan": [
        "doanh thu thuần", "net sales", "net revenue", "doanh thu bán hàng",
        "thu nhập lãi thuần", "thu nhập từ lãi",
        "tổng thu nhập hoạt động",
    ],
    "gia_von_hang_ban": [
        "giá vốn hàng bán", "cost of goods sold", "cost of sales",
        "chi phí lãi",
    ],
    "loi_nhuan_gop": [
        "lợi nhuận gộp", "gross profit",
    ],
    "loi_nhuan_thuan_hdkd": [
        "lợi nhuận thuần từ hoạt động kinh doanh", "operating profit",
        "lợi nhuận từ hoạt động kinh doanh",
    ],
    "loi_nhuan_truoc_thue": [
        "lợi nhuận trước thuế", "profit before tax", "ebit",
        "lợi nhuận trước thuế thu nhập doanh nghiệp",
    ],
    "loi_nhuan_sau_thue": [
        "lợi nhuận sau thuế thu nhập doanh nghiệp", "lợi nhuận sau thuế",
        "net profit", "profit after tax", "net income", "lnst",
    ],
    "loi_nhuan_sau_thue_cong_ty_me": [
        "lợi nhuận sau thuế của cổ đông công ty mẹ",
        "net profit attributable to parent", "attributable to parent",
        "lợi nhuận thuộc về cổ đông công ty mẹ",
    ],
    "chi_phi_hoat_dong": [
        "chi phí hoạt động", "operating expenses", "chi phí bán hàng",
        "chi phí quản lý", "chi phí quản lý doanh nghiệp",
    ],

    # --- Bảng cân đối kế toán ---
    "tong_tai_san": [
        "tổng cộng tài sản", "total assets", "tổng tài sản",
    ],
    "no_phai_tra": [
        "nợ phải trả", "total liabilities", "tổng nợ phải trả",
    ],
    "von_chu_so_huu": [
        "vốn chủ sở hữu", "owner's equity", "total equity",
        "vcsh", "equity", "tổng vốn chủ sở hữu",
    ],
    "tai_san_ngan_han": [
        "tài sản ngắn hạn", "current assets",
    ],
    "tai_san_dai_han": [
        "tài sản dài hạn", "non-current assets", "tài sản cố định",
    ],
    "no_ngan_han": [
        "nợ ngắn hạn", "current liabilities",
    ],
    "no_dai_han": [
        "nợ dài hạn", "non-current liabilities", "nợ dài hạn phải trả",
    ],
    "hang_ton_kho": [
        "hàng tồn kho", "inventories",
    ],
    "tien_va_tuong_duong_tien": [
        "tiền và các khoản tương đương tiền", "cash and cash equivalents",
        "tiền mặt", "tiền gửi",
    ],
    "cho_vay_khach_hang": [
        "cho vay khách hàng", "loans to customers", "dư nợ cho vay",
    ],
    "tien_gui_khach_hang": [
        "tiền gửi của khách hàng", "deposits from customers", "huy động vốn",
    ],

    # --- Lưu chuyển tiền tệ ---
    "luu_chuyen_tien_kinh_doanh": [
        "lưu chuyển tiền thuần từ hoạt động kinh doanh",
        "net cash flow from operating", "tiền từ hoạt động kinh doanh",
    ],
    "luu_chuyen_tien_dau_tu": [
        "lưu chuyển tiền thuần từ hoạt động đầu tư",
        "net cash flow from investing", "tiền từ hoạt động đầu tư",
    ],
    "luu_chuyen_tien_tai_chinh": [
        "lưu chuyển tiền thuần từ hoạt động tài chính",
        "net cash flow from financing", "tiền từ hoạt động tài chính",
    ],
}

# ---------------------------------------------------------------------------
# RATIO_DEFINITIONS: công thức tính tỷ số tài chính
# ---------------------------------------------------------------------------
RATIO_DEFINITIONS = {
    "roe": {
        "label": "ROE (Lợi nhuận trên vốn chủ sở hữu)",
        "numerator": "loi_nhuan_sau_thue",
        "denominator": "von_chu_so_huu",
        "format": "percent",
        "description": "Lợi nhuận sau thuế / Vốn chủ sở hữu",
    },
    "roa": {
        "label": "ROA (Lợi nhuận trên tổng tài sản)",
        "numerator": "loi_nhuan_sau_thue",
        "denominator": "tong_tai_san",
        "format": "percent",
        "description": "Lợi nhuận sau thuế / Tổng tài sản",
    },
    "current_ratio": {
        "label": "Tỷ lệ thanh khoản hiện hành",
        "numerator": "tai_san_ngan_han",
        "denominator": "no_ngan_han",
        "format": "ratio",
        "description": "Tài sản ngắn hạn / Nợ ngắn hạn",
    },
    "debt_ratio": {
        "label": "Tỷ lệ nợ",
        "numerator": "no_phai_tra",
        "denominator": "tong_tai_san",
        "format": "percent",
        "description": "Nợ phải trả / Tổng tài sản",
    },
    "profit_margin": {
        "label": "Biên lợi nhuận ròng",
        "numerator": "loi_nhuan_sau_thue",
        "denominator": "doanh_thu_thuan",
        "format": "percent",
        "description": "Lợi nhuận sau thuế / Doanh thu thuần",
    },
}

# ---------------------------------------------------------------------------
# COMPANY_ALIASES: map tên thường gặp -> ticker
# ---------------------------------------------------------------------------
COMPANY_ALIASES = {
    # VCB
    "vietcombank": "VCB", "vcb": "VCB", "ngoại thương": "VCB",
    # BID
    "bidv": "BID", "bid": "BID", "đầu tư phát triển": "BID",
    "dau tu phat trien": "BID",
    # CTG
    "vietinbank": "CTG", "ctg": "CTG", "công thương": "CTG",
    "cong thuong": "CTG",
    # VNM
    "vinamilk": "VNM", "vnm": "VNM", "sữa việt nam": "VNM",
    "sua viet nam": "VNM",
    # FPT
    "fpt": "FPT",
    # VIC
    "vingroup": "VIC", "vic": "VIC",
    # MSN
    "masan": "MSN", "msn": "MSN",
    # VJC
    "vietjet": "VJC", "vjc": "VJC", "vietjet air": "VJC",
    # SAB
    "sabeco": "SAB", "sab": "SAB", "bia sài gòn": "SAB",
    "bia sai gon": "SAB",
    # HPG
    "hòa phát": "HPG", "hoa phat": "HPG", "hpg": "HPG",
    # MWG
    "mobile world": "MWG", "mwg": "MWG",
    "thế giới di động": "MWG", "the gioi di dong": "MWG",
    # VRE
    "vincom retail": "VRE", "vre": "VRE", "vincom": "VRE",
    # HDB
    "hdbank": "HDB", "hdb": "HDB",
    # TCB
    "techcombank": "TCB", "tcb": "TCB",
    # VPB
    "vpbank": "VPB", "vpb": "VPB",
}

# Nguồn dữ liệu mặc định
DEFAULT_SOURCE = "VCI"

# EcoData API settings
# NOTE: EcoData.ai API endpoint chưa được verify. Set ECODATA_ENABLED=False cho đến khi có docs chính thức.
ECODATA_ENABLED = False  # Set to True khi có endpoint + docs thực
PREFER_ECODATA = False   # If True, try EcoData first; if False, try vnstock first

# ---------------------------------------------------------------------------
# Retrieval Layer
# ---------------------------------------------------------------------------
BGE_MODEL = os.getenv("BGE_MODEL", "BAAI/bge-small-en-v1.5")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")
QUERY_EXPANSION_ENABLED = os.getenv("QUERY_EXPANSION_ENABLED", "true").lower() == "true"
