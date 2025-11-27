# config.py

# Companies
COMPANIES = [
    "LESTARY",
    "JH CINTA MATA",
    "PEMBANGUNAN KESAN ANEKA",
    "PASTI JUTANIAGA"
]

# Categories/types used in select fields
CATEGORIES = ["Vehicle", "Machinery"]
TYPES = [
    "Car","Lorry","Motorbike","Backhoe","Excavator","Cold Recycle Machine","Compactor",
    "Shovel","Dozer","Hino","Motor Grader","Milling Machine","HOWO Truck","Kubota",
    "Paver","Mixer","Mobile Crusher"
]

# default emails (placeholders)
PLACEHOLDER_SENDER = "youremail@example.com"
DEFAULT_REPORT_EMAIL = "chichilee9888@gmail.com"   # YOU chose this as monthly recipient

# small sample dataset
SAMPLE_ITEMS = [
    {
        "company":"LESTARY","category":"Vehicle","type":"Car","code":"LST-001",
        "model":"Toyota Hilux","plate_no":"ABC123","serial_no":"",
        "current_location":"HQ","driver":"Ali","permit_expiry":None,
        "puspakom_expiry":None,"insurance_expiry":None,"loan_due_date":None,
        "loan_monthly_amount":0,"status":"Active","remarks":"Sample"
    },
    {
        "company":"JH CINTA MATA","category":"Machinery","type":"Excavator","code":"JH-EX-01",
        "model":"CAT 320","plate_no":"","serial_no":"SN-EX-001",
        "current_location":"Site A","driver":"Bob","permit_expiry":None,
        "puspakom_expiry":None,"insurance_expiry":None,"loan_due_date":None,
        "loan_monthly_amount":0,"status":"Active","remarks":"Sample"
    }
]
