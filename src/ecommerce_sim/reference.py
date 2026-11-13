"""Fixed reference data: places, channels, sizes, tax rates, festivals and so on.

Everything here is plain data (lists and dictionaries) so it is easy to read and edit.
"""

# ----------------------------------------------------------------------------- places
# city: (state, region, tier, pincode prefix, nearest warehouse)
CITIES = {
    "Mumbai": ("Maharashtra", "West", "Tier 1", "400", "WH_MUM"),
    "Pune": ("Maharashtra", "West", "Tier 1", "411", "WH_MUM"),
    "Ahmedabad": ("Gujarat", "West", "Tier 1", "380", "WH_MUM"),
    "Surat": ("Gujarat", "West", "Tier 2", "395", "WH_MUM"),
    "Nagpur": ("Maharashtra", "West", "Tier 2", "440", "WH_MUM"),
    "Indore": ("Madhya Pradesh", "West", "Tier 2", "452", "WH_MUM"),
    "New Delhi": ("Delhi", "North", "Tier 1", "110", "WH_DEL"),
    "Noida": ("Uttar Pradesh", "North", "Tier 2", "201", "WH_DEL"),
    "Lucknow": ("Uttar Pradesh", "North", "Tier 2", "226", "WH_DEL"),
    "Jaipur": ("Rajasthan", "North", "Tier 2", "302", "WH_DEL"),
    "Chandigarh": ("Punjab", "North", "Tier 2", "160", "WH_DEL"),
    "Dehradun": ("Uttarakhand", "North", "Tier 3", "248", "WH_DEL"),
    "Bengaluru": ("Karnataka", "South", "Tier 1", "560", "WH_BLR"),
    "Chennai": ("Tamil Nadu", "South", "Tier 1", "600", "WH_BLR"),
    "Hyderabad": ("Telangana", "South", "Tier 1", "500", "WH_BLR"),
    "Kochi": ("Kerala", "South", "Tier 2", "682", "WH_BLR"),
    "Coimbatore": ("Tamil Nadu", "South", "Tier 2", "641", "WH_BLR"),
    "Mysuru": ("Karnataka", "South", "Tier 3", "570", "WH_BLR"),
    "Vijayawada": ("Andhra Pradesh", "South", "Tier 3", "520", "WH_BLR"),
    "Kolkata": ("West Bengal", "East", "Tier 1", "700", "WH_KOL"),
    "Bhubaneswar": ("Odisha", "East", "Tier 2", "751", "WH_KOL"),
    "Patna": ("Bihar", "East", "Tier 3", "800", "WH_KOL"),
    "Ranchi": ("Jharkhand", "East", "Tier 3", "834", "WH_KOL"),
    "Guwahati": ("Assam", "East", "Tier 3", "781", "WH_KOL"),
}
# Bigger cities send more customers.
TIER_WEIGHT = {"Tier 1": 3.0, "Tier 2": 1.4, "Tier 3": 0.8}

WAREHOUSES = {
    # id: (city, region, capacity in units)
    "WH_MUM": ("Mumbai", "West", 400_000),
    "WH_DEL": ("New Delhi", "North", 400_000),
    "WH_BLR": ("Bengaluru", "South", 350_000),
    "WH_KOL": ("Kolkata", "East", 250_000),
}

# ----------------------------------------------------------------------------- products
# Sizes offered for each kind of product (by the catalogue's sub-category / article type).
APPAREL_SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
FOOTWEAR_SIZES = ["6", "7", "8", "9", "10", "11"]
FREE_SIZE = ["Free Size"]
# Share of customers wearing each size (used for the hidden size profile).
APPAREL_SIZE_SHARE = [0.06, 0.20, 0.30, 0.25, 0.13, 0.06]
FOOTWEAR_SIZE_SHARE = [0.08, 0.17, 0.25, 0.25, 0.17, 0.08]

MATERIALS = {
    "Topwear": ["Cotton", "Cotton Blend", "Polyester", "Linen", "Viscose"],
    "Bottomwear": ["Denim", "Cotton", "Polyester", "Lycra Blend"],
    "Dress": ["Viscose", "Polyester", "Cotton", "Georgette"],
    "Saree": ["Silk", "Georgette", "Cotton", "Chiffon"],
    "Innerwear": ["Cotton", "Modal", "Lycra Blend"],
    "Loungewear and Nightwear": ["Cotton", "Modal", "Satin"],
    "Shoes": ["Leather", "Synthetic", "Mesh", "Canvas"],
    "Sandal": ["Leather", "Synthetic", "Rubber"],
    "Flip Flops": ["Rubber", "EVA"],
    "Bags": ["Leather", "Synthetic Leather", "Canvas", "Nylon"],
    "Watches": ["Stainless Steel", "Leather Strap", "Silicone"],
    "Eyewear": ["Metal", "Acetate", "Polycarbonate"],
    "Jewellery": ["Brass", "Silver Plated", "Alloy"],
}
DEFAULT_MATERIALS = ["Cotton", "Polyester", "Synthetic", "Metal"]
FITS = ["Regular", "Slim", "Relaxed", "Oversized"]

# GST (goods and services tax) in India for fashion, simplified:
# clothing and footwear 5% up to Rs 1,000 and 12% above; accessories 18%.
def gst_rate(category: str, price: float) -> float:
    if category in ("Apparel", "Footwear"):
        return 0.05 if price <= 1000 else 0.12
    return 0.18


# Starting list prices (MRP) by category, before random variation.
BASE_PRICE = {"Apparel": 1100, "Footwear": 2300, "Accessories": 1600}
PREMIUM_TYPES = {"Watches": 3.0, "Handbags": 2.3, "Sports Shoes": 1.9, "Formal Shoes": 1.9,
                 "Heels": 1.5, "Sunglasses": 1.5, "Jackets": 1.6, "Sarees": 1.7}

# Article types usually bought together (used by the simulator's shoppers, never by models).
COMPLEMENTS = {
    "Tshirts": ["Jeans", "Track Pants", "Casual Shoes", "Caps"],
    "Shirts": ["Jeans", "Trousers", "Belts", "Formal Shoes"],
    "Tops": ["Jeans", "Handbags", "Heels"],
    "Kurtas": ["Leggings", "Sandals", "Earrings"],
    "Kurtis": ["Leggings", "Sandals"],
    "Dresses": ["Heels", "Handbags", "Sunglasses"],
    "Jeans": ["Tshirts", "Shirts", "Belts", "Casual Shoes"],
    "Trousers": ["Shirts", "Formal Shoes", "Belts"],
    "Track Pants": ["Tshirts", "Sports Shoes"],
    "Casual Shoes": ["Socks", "Jeans"],
    "Sports Shoes": ["Socks", "Track Pants"],
    "Formal Shoes": ["Socks", "Belts", "Shirts"],
    "Heels": ["Dresses", "Handbags"],
    "Watches": ["Sunglasses", "Belts", "Wallets"],
    "Handbags": ["Sunglasses", "Wallets"],
    "Sunglasses": ["Watches", "Caps"],
    "Belts": ["Wallets", "Formal Shoes"],
    "Sarees": ["Handbags", "Earrings"],
}

# ----------------------------------------------------------------------------- customers
SIGNUP_METHODS = ["Phone OTP", "Email OTP"]
SIGNUP_METHOD_SHARE = [0.68, 0.32]
AGE_BRACKETS = ["18-24", "25-34", "35-44", "45-54", "55+"]
AGE_SHARE = [0.20, 0.38, 0.24, 0.12, 0.06]
GENDERS = ["F", "M", "Other"]
GENDER_SHARE = [0.52, 0.46, 0.02]
DEVICES = ["Android App", "iOS App", "Mobile Web", "Desktop Web"]
DEVICE_SHARE = [0.45, 0.20, 0.22, 0.13]

# Fictional people: names are combined at random; emails use example.com and phone
# numbers start with +91 00000, which is not a valid Indian mobile prefix.
FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Kabir", "Ishaan", "Rahul", "Siddharth", "Karan",
               "Ananya", "Diya", "Isha", "Kavya", "Meera", "Priya", "Riya", "Sneha", "Tanvi", "Neha",
               "Zoya", "Farhan", "Imran", "Sana", "Joseph", "Maria", "Harpreet", "Gurpreet", "Lakshmi", "Arun"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Singh", "Das", "Banerjee",
              "Kulkarni", "Joshi", "Mehta", "Khan", "Fernandes", "Menon", "Rao", "Chopra", "Bose", "Shetty"]
STREETS = ["MG Road", "Station Road", "Park Street", "Lake View", "Civil Lines", "Ring Road", "Market Lane",
           "Temple Street", "Gandhi Nagar", "Sector 21"]

# ----------------------------------------------------------------------------- sellers
SELLER_TYPES = ["1P", "3P-FBA", "3P-MFN"]          # own stock, marketplace + our warehouse, seller ships
SELLER_TYPE_SHARE = [0.20, 0.45, 0.35]
SELLER_WORDS_1 = ["Urban", "Metro", "Prime", "Nova", "Royal", "Vogue", "Trend", "Desi", "Classic", "Street"]
SELLER_WORDS_2 = ["Retail", "Traders", "Fashions", "Enterprises", "Apparel", "Lifestyle", "Store", "House"]

# ----------------------------------------------------------------------------- orders
PAYMENT_METHODS = ["UPI", "COD", "Credit Card", "Debit Card", "Net Banking", "Wallet"]
PAYMENT_SHARE_TIER = {
    "Tier 1": [0.42, 0.12, 0.20, 0.12, 0.06, 0.08],
    "Tier 2": [0.40, 0.25, 0.12, 0.11, 0.05, 0.07],
    "Tier 3": [0.34, 0.40, 0.07, 0.09, 0.04, 0.06],
}
PAYMENT_FAILURE_RATE = {"UPI": 0.06, "COD": 0.0, "Credit Card": 0.05, "Debit Card": 0.07,
                        "Net Banking": 0.09, "Wallet": 0.04}
COURIERS = ["Delhivery", "BlueDart", "Ekart", "Shadowfax", "XpressBees"]
COURIER_SHARE = [0.32, 0.18, 0.24, 0.12, 0.14]
COURIER_SPEED = {"Delhivery": 0.0, "BlueDart": -0.6, "Ekart": 0.2, "Shadowfax": 0.4, "XpressBees": 0.3}
FREE_SHIPPING_ABOVE = 499
SHIPPING_FEE = 49
RETURN_WINDOW_DAYS = 7
RETURN_REASONS = ["Size Issue", "Fit Issue", "Quality Issue", "Damaged", "Wrong Product",
                  "Colour Mismatch", "Changed Mind"]
CANCEL_REASONS = ["Ordered by mistake", "Found cheaper elsewhere", "Delivery too slow", "Changed mind"]

# ----------------------------------------------------------------------------- marketing
# channel: (channel group, cost per 1,000 impressions in Rs, click-through rate, utm_source, utm_medium)
PAID_CHANNELS = {
    "Google Search": ("Paid Search", 420.0, 0.045, "google", "cpc"),
    "Google Shopping": ("Paid Search", 300.0, 0.020, "google", "shopping"),
    "Bing Search": ("Paid Search", 260.0, 0.035, "bing", "cpc"),
    "Meta": ("Paid Social", 170.0, 0.011, "facebook", "paid_social"),
    "Instagram": ("Paid Social", 190.0, 0.012, "instagram", "paid_social"),
    "YouTube": ("Paid Social", 110.0, 0.006, "youtube", "video"),
    "DSP Display": ("Display", 85.0, 0.004, "dsp", "display"),
}
# Affiliates are paid per sale (CPS), per new customer (CPA) or per click (CPC).
AFFILIATE_PARTNERS = {
    # partner: (partner type, payout model, payout rate, typical clicks per day)
    "SaveMore Cashback": ("Cashback", "CPS", 0.07, 40),
    "DealDhamaka Coupons": ("Coupon Site", "CPS", 0.05, 30),
    "StyleStory Blog Network": ("Content", "CPS", 0.08, 12),
    "CreatorCart Influencers": ("Influencer", "CPA", 150.0, 15),
    "PriceSaathi Compare": ("Price Comparison", "CPC", 4.0, 20),
}
CRM_CHANNELS = {
    # channel: (utm_source, open rate, click rate among opens, cost per message in Rs)
    "Email": ("newsletter", 0.22, 0.14, 0.05),
    "Push": ("app_push", 0.09, 0.30, 0.0),
    "SMS": ("sms", 0.0, 0.035, 0.12),          # SMS has no "open"; clicks are on the link
    "WhatsApp": ("whatsapp", 0.70, 0.08, 0.35),
}
ORGANIC_SOURCES = {
    # traffic source: (utm_source, utm_medium) -- organic visits carry no campaign
    "organic_search": ("google", "organic"),
    "direct": ("(direct)", "(none)"),
    "referral": ("friend", "referral"),
}

# ----------------------------------------------------------------------------- events
# Festivals with dates that move each year (lunar calendar): name -> {year: (start, end)}.
MOVING_FESTIVALS = {
    "Holi": {2025: ("03-10", "03-14"), 2026: ("02-28", "03-04"), 2027: ("03-18", "03-22")},
    "Eid al-Fitr": {2025: ("03-26", "03-31"), 2026: ("03-15", "03-20"), 2027: ("03-05", "03-10")},
    "Raksha Bandhan": {2025: ("08-05", "08-09"), 2026: ("08-24", "08-28"), 2027: ("08-13", "08-17")},
    "Onam": {2025: ("08-29", "09-05"), 2026: ("08-21", "08-26"), 2027: ("09-07", "09-12")},
    "Navratri & Dussehra": {2025: ("09-22", "10-02"), 2026: ("10-11", "10-20"), 2027: ("09-30", "10-09")},
    "Grand Festive Sale": {2025: ("09-23", "10-02"), 2026: ("10-08", "10-17"), 2027: ("09-28", "10-07")},
    "Diwali": {2025: ("10-15", "10-21"), 2026: ("11-03", "11-08"), 2027: ("10-24", "10-29")},
    "Black Friday & Cyber Monday": {2025: ("11-28", "12-01"), 2026: ("11-27", "11-30"), 2027: ("11-26", "11-29")},
    "Mother's Day": {2025: ("05-09", "05-11"), 2026: ("05-07", "05-10"), 2027: ("05-06", "05-09")},
    "Father's Day": {2025: ("06-13", "06-15"), 2026: ("06-19", "06-21"), 2027: ("06-18", "06-20")},
    "Mid-Year Member Days": {2025: ("07-12", "07-14"), 2026: ("07-11", "07-13"), 2027: ("07-10", "07-12")},
    "Republic Day Sale": {2025: ("01-17", "01-20"), 2026: ("01-16", "01-19"), 2027: ("01-15", "01-18")},
    "Independence Day Sale": {2025: ("08-08", "08-15"), 2026: ("08-07", "08-15"), 2027: ("08-08", "08-15")},
    "Summer End of Season Sale": {2025: ("06-13", "06-22"), 2026: ("06-12", "06-21"), 2027: ("06-11", "06-20")},
    "Winter End of Season Sale": {2025: ("01-24", "02-02"), 2026: ("01-23", "02-01"), 2027: ("01-22", "01-31")},
}
# Festivals on the same calendar dates every year.
FIXED_FESTIVALS = {
    "New Year Sale": ("01-01", "01-03"),
    "Makar Sankranti & Pongal": ("01-13", "01-15"),
    "Valentine's Day": ("02-10", "02-14"),
    "Women's Day": ("03-06", "03-08"),
    "Christmas": ("12-20", "12-25"),
    "Year End Sale": ("12-26", "12-31"),
}
# event name -> (type, categories on offer ("All" = everything), average extra discount,
#                demand uplift during the event, days of run-up, Prime early-access days)
EVENT_RULES = {
    "New Year Sale": ("Season Sale", "All", 0.15, 1.35, 3, 0),
    "Makar Sankranti & Pongal": ("Festival", "Ethnic", 0.12, 1.20, 3, 0),
    "Republic Day Sale": ("Mega Sale", "All", 0.25, 1.80, 5, 1),
    "Winter End of Season Sale": ("Clearance", "Winter", 0.35, 1.55, 3, 0),
    "Valentine's Day": ("Festival", "Gifting", 0.12, 1.30, 4, 0),
    "Women's Day": ("Festival", "Women", 0.15, 1.25, 3, 0),
    "Holi": ("Festival", "Casual", 0.10, 1.20, 4, 0),
    "Eid al-Fitr": ("Festival", "Ethnic", 0.15, 1.35, 5, 0),
    "Mother's Day": ("Festival", "Gifting", 0.12, 1.25, 4, 0),
    "Summer End of Season Sale": ("Clearance", "Summer", 0.40, 1.75, 4, 1),
    "Father's Day": ("Festival", "Gifting", 0.12, 1.20, 4, 0),
    "Mid-Year Member Days": ("Mega Sale", "All", 0.30, 1.90, 5, 3),
    "Raksha Bandhan": ("Festival", "Gifting", 0.12, 1.30, 5, 0),
    "Independence Day Sale": ("Mega Sale", "All", 0.25, 1.85, 5, 1),
    "Onam": ("Festival", "Ethnic", 0.12, 1.20, 4, 0),
    "Navratri & Dussehra": ("Festival", "Ethnic", 0.18, 1.45, 5, 0),
    "Grand Festive Sale": ("Mega Sale", "All", 0.35, 2.40, 7, 1),
    "Diwali": ("Festival", "Ethnic", 0.25, 2.00, 7, 0),
    "Black Friday & Cyber Monday": ("Mega Sale", "All", 0.30, 1.90, 5, 0),
    "Christmas": ("Festival", "Gifting", 0.15, 1.40, 5, 0),
    "Year End Sale": ("Season Sale", "All", 0.20, 1.50, 3, 0),
    "Payday Sale": ("Payday", "All", 0.08, 1.15, 0, 0),
}
# Which products each event's "categories on offer" covers.
GIFTING_TYPES = {"Watches", "Handbags", "Wallets", "Perfume and Body Mist", "Sunglasses", "Earrings",
                 "Clutches", "Belts", "Jewellery Set", "Bracelet", "Ties"}
WINTER_TYPES = {"Jackets", "Sweaters", "Sweatshirts", "Boots", "Shrug", "Mufflers", "Gloves"}
SUMMER_TYPES = {"Tshirts", "Tops", "Dresses", "Shorts", "Sandals", "Flip Flops", "Sunglasses", "Caps"}
# Couriers deliver slowly on the biggest festival days.
COURIER_SLOWDOWN_EVENTS = {"Diwali", "Holi", "Eid al-Fitr"}

# ----------------------------------------------------------------------------- support
SUPPORT_TEAMS = ["Orders", "Returns", "Payments", "Product Support"]
AGENT_LOCATIONS = ["Mumbai", "Bengaluru", "New Delhi", "Hyderabad", "Kolkata"]
AGENT_LANGUAGES = ["English", "Hindi", "Tamil", "Bengali", "Marathi"]
