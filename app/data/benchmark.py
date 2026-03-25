import pandas as pd

def load_benchmark():
    data = [
        # UHC
        {"payer": "UHC", "cpt_code": "99213", "modifier": "", "place_of_service": "11", "benchmark_amount": 82.00},
        {"payer": "UHC", "cpt_code": "99214", "modifier": "", "place_of_service": "11", "benchmark_amount": 104.00},
        {"payer": "UHC", "cpt_code": "99215", "modifier": "", "place_of_service": "11", "benchmark_amount": 148.00},
        {"payer": "UHC", "cpt_code": "17000", "modifier": "", "place_of_service": "11", "benchmark_amount": 83.00},
        {"payer": "UHC", "cpt_code": "17003", "modifier": "", "place_of_service": "11", "benchmark_amount": 12.00},
        {"payer": "UHC", "cpt_code": "11102", "modifier": "", "place_of_service": "11", "benchmark_amount": 135.00},
        {"payer": "UHC", "cpt_code": "11103", "modifier": "", "place_of_service": "11", "benchmark_amount": 45.00},
        {"payer": "UHC", "cpt_code": "17110", "modifier": "", "place_of_service": "11", "benchmark_amount": 120.00},
        {"payer": "UHC", "cpt_code": "17111", "modifier": "", "place_of_service": "11", "benchmark_amount": 155.00},

        # AETNA
        {"payer": "AETNA", "cpt_code": "99213", "modifier": "", "place_of_service": "11", "benchmark_amount": 84.00},
        {"payer": "AETNA", "cpt_code": "99214", "modifier": "", "place_of_service": "11", "benchmark_amount": 110.00},
        {"payer": "AETNA", "cpt_code": "17000", "modifier": "", "place_of_service": "11", "benchmark_amount": 86.00},
        {"payer": "AETNA", "cpt_code": "17003", "modifier": "", "place_of_service": "11", "benchmark_amount": 14.00},
        {"payer": "AETNA", "cpt_code": "11102", "modifier": "", "place_of_service": "11", "benchmark_amount": 140.00},
        {"payer": "AETNA", "cpt_code": "11103", "modifier": "", "place_of_service": "11", "benchmark_amount": 48.00},
        {"payer": "AETNA", "cpt_code": "17110", "modifier": "", "place_of_service": "11", "benchmark_amount": 124.00},
        {"payer": "AETNA", "cpt_code": "17111", "modifier": "", "place_of_service": "11", "benchmark_amount": 160.00},

        # BCBS
        {"payer": "BCBS", "cpt_code": "99213", "modifier": "", "place_of_service": "11", "benchmark_amount": 83.00},
        {"payer": "BCBS", "cpt_code": "99214", "modifier": "", "place_of_service": "11", "benchmark_amount": 108.00},
        {"payer": "BCBS", "cpt_code": "17000", "modifier": "", "place_of_service": "11", "benchmark_amount": 85.00},
        {"payer": "BCBS", "cpt_code": "17003", "modifier": "", "place_of_service": "11", "benchmark_amount": 13.00},
        {"payer": "BCBS", "cpt_code": "11102", "modifier": "", "place_of_service": "11", "benchmark_amount": 138.00},
        {"payer": "BCBS", "cpt_code": "11103", "modifier": "", "place_of_service": "11", "benchmark_amount": 47.00},
        {"payer": "BCBS", "cpt_code": "17110", "modifier": "", "place_of_service": "11", "benchmark_amount": 122.00},
        {"payer": "BCBS", "cpt_code": "17111", "modifier": "", "place_of_service": "11", "benchmark_amount": 158.00},
    ]

    return pd.DataFrame(data)