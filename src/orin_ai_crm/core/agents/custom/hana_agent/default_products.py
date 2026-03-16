"""
Default Products for ORIN GPS Tracker

This file contains the default product catalog.
These products are loaded into the database on first startup or when reset.

To add a new product:
1. Add a dict to the DEFAULT_PRODUCTS list
2. Ensure all required fields are present
3. Use triple quotes for multi-line description if needed
"""

DEFAULT_PRODUCTS = [
    {
        "name": "OBU M",
        "sku": "OBU-M",
        "category": "TANAM",
        "subcategory": "OBU",
        "vehicle_type": "motor listrik,mobil listrik",
        "description": "GPS Tracker dengan fitur pelacakan real-time. Termasuk FREE Pelacak mini Orin Tag Android.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Riwayat perjalanan seminggu terakhir"],
            "bonus": "FREE Pelacak mini Orin Tag Android",
            "server": "ORIN LITE"
        },
        "price": "25rb/bulan (perpanjangan setelah 1 bulan pertama)",
        "installation_type": "pasang_technisi",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Vehicle battery",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "25rb/bulan",
        "ecommerce_links": {
            "tokopedia": "https://id.shp.ee/5mJ3NnE",
            "shopee": "https://tk.tokopedia.com/ZSa1x5Rpd/"
        },
        "specifications": {
            "kuota_awal": "Gratis 1 bulan",
            "garansi": "Seumur hidup",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server, ada garansi 1th"
        },
        "is_active": True,
        "sort_order": 1
    },
    {
        "name": "OBU V",
        "sku": "OBU-V",
        "category": "TANAM",
        "subcategory": "OBU",
        "vehicle_type": "mobil,motor",
        "description": "GPS Tracker dengan fitur matikan mesin jarak jauh dan sadap suara. Pemasangan oleh teknisi.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Matikan mesin jarak jauh", "Sadap suara", "Riwayat perjalanan seminggu terakhir"],
            "server": "ORIN LITE"
        },
        "price": "25rb/bulan (perpanjangan setelah 1 bulan pertama)",
        "installation_type": "pasang_technisi",
        "can_shutdown_engine": True,
        "can_wiretap": True,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Vehicle battery",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "25rb/bulan",
        "ecommerce_links": {
            "tokopedia": "https://tk.tokopedia.com/ZSfrb4RGp/",
            "tiktokshop": "https://vt.tokopedia.com/t/ZSHw7cTrBkss4-Of0ut/",
            "shopee": "https://id.shp.ee/gmGRm9J"
        },
        "specifications": {
            "kuota_awal": "Gratis 1 bulan",
            "garansi": "Seumur hidup",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server, ada garansi 1th"
        },
        "is_active": True,
        "sort_order": 2
    },
    {
        "name": "OBU F",
        "sku": "OBU-F",
        "category": "TANAM",
        "subcategory": "OBU",
        "vehicle_type": "mobil,truk,alat berat",
        "description": "GPS Tracker premium dengan fitur matikan mesin, monitoring BBM, dan memori internal untuk area lemah sinyal.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Matikan mesin jarak jauh", "Monitoring BBM (add on)", "Memori internal penyimpan data", "Riwayat perjalanan 3 bulan terakhir", "5 geofence/pagar maya", "Data report/laporan detail"],
            "server": "ORIN PLUS"
        },
        "price": "350k/6 bulan atau 600rb/tahun (perpanjangan setelah 1 tahun pertama)",
        "installation_type": "pasang_technisi",
        "can_shutdown_engine": True,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Vehicle battery",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "350k/6 bulan atau 600rb/tahun",
        "ecommerce_links": {
            "tokopedia": "https://tk.tokopedia.com/ZS5qRnT6e/",
            "shopee": "https://id.shp.ee/YZF3wbA"
        },
        "specifications": {
            "kuota_awal": "Gratis 1 tahun",
            "garansi": "Seumur Hidup",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server, ada garansi 1th"
        },
        "is_active": True,
        "sort_order": 3
    },
    {
        "name": "OBU D",
        "sku": "OBU-D",
        "category": "INSTAN",
        "subcategory": "OBU",
        "vehicle_type": "mobil dengan port OBD,kendaraan dengan port OBD",
        "description": "GPS Tracker plug-and-play. Bisa pasang mandiri, tinggal colok ke port OBD mobil.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Riwayat perjalanan 3 bulan terakhir", "5 geofence/pagar maya", "Data report/laporan detail"],
            "server": "ORIN PLUS",
            "pemasangan": "Bisa pasang mandiri, colok ke port OBD"
        },
        "price": "350k/6 bulan atau 600rb/tahun (perpanjangan setelah 6 bulan pertama)",
        "installation_type": "colok_sendiri",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Vehicle battery (OBD port)",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "350k/6 bulan atau 600rb/tahun",
        "ecommerce_links": {
            "shopee": "https://id.shp.ee/kBFg5iz"
        },
        "specifications": {
            "kuota_awal": "Gratis 6 bulan",
            "garansi": "1 tahun",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server, ada garansi 1th"
        },
        "is_active": True,
        "sort_order": 4
    },
    {
        "name": "OBU T1",
        "sku": "OBU-T1",
        "category": "INSTAN",
        "subcategory": "OBU",
        "vehicle_type": "mobil dengan port lighter,motor dengan port lighter,kendaraan dengan port lighter",
        "description": "GPS Tracker compact type yang dipasang di port lighter mobil. Plug-and-play dengan fitur lengkap.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Riwayat perjalanan 3 bulan terakhir", "5 geofence/pagar maya", "Data report/laporan detail"],
            "server": "ORIN PLUS",
            "pemasangan": "Dipasang di port lighter"
        },
        "price": "350k/6 bulan atau 600rb/tahun (perpanjangan setelah 1 tahun pertama)",
        "installation_type": "pasang_mandiri",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Lighter port",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "350k/6 bulan atau 600rb/tahun",
        "ecommerce_links": {
            "tokopedia": "https://tk.tokopedia.com/ZS5WBFQRv/"
        },
        "specifications": {
            "kuota_awal": "Gratis 1 tahun",
            "garansi": "1 tahun",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota, server, dan garansi"
        },
        "is_active": True,
        "sort_order": 5
    },
    {
        "name": "OBU T",
        "sku": "OBU-T",
        "category": "INSTAN",
        "subcategory": "OBU",
        "vehicle_type": "semua jenis kendaraan",
        "description": "GPS Tracker portable dengan baterai tahan lama. Bisa dipasang dimanapun pada aset berharga. Cocok untuk kebutuhan pelacakan fleksibel.",
        "features": {
            "fitur_utama": ["Lacak real-time", "Riwayat perjalanan 3 bulan terakhir", "5 geofence/pagar maya", "Data report/laporan detail"],
            "server": "ORIN PLUS",
            "pemasangan": "Portable, ditaruh di tempat tersembunyi"
        },
        "price": "350k/6 bulan atau 600rb/tahun (perpanjangan setelah 1 tahun pertama)",
        "installation_type": "pasang_mandiri",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": True,
        "battery_life": "3 minggu",
        "power_source": "Battery (chargeable)",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "350k/6 bulan atau 600rb/tahun",
        "ecommerce_links": {
            "shopee": "https://id.shp.ee/J3LGuj4"
        },
        "specifications": {
            "kuota_awal": "Include 1 tahun",
            "garansi": "Seumur hidup",
            "komponen": ["Sim Card"],
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server, ada garansi 1th"
        },
        "is_active": True,
        "sort_order": 6
    },
    {
        "name": "ORIN TAG ANDROID",
        "sku": "ORIN-TAG-ANDROID",
        "category": "AKSESORIS",
        "subcategory": "TAG",
        "vehicle_type": "mobil,motor,aset berharga,semua kendaraan",
        "description": "Pelacak mini dengan support bluetooth untuk HP Android. Compact tracker yang bisa dipasang pada berbagai benda berharga. Tanpa biaya bulanan.",
        "features": {
            "fitur_utama": ["Menunjukan lokasi terakhir", "Ukuran kecil", "Sensor Bunyi Nyaring (under control)", "Tanpa Biaya Bulanan", "Ukuran Mini & Ringan", "Jangkauan Global"],
            "kompatibilitas": "Android",
            "tipe": "Bluetooth/GPS tracker"
        },
        "price": None,
        "installation_type": "pasang_mandiri",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": True,
        "battery_life": "6 bulan",
        "power_source": "Battery (CR2032)",
        "tracking_type": "Bluetooth (bukan GPS satelit)",
        "monthly_fee": None,
        "ecommerce_links": {
            "shopee": "https://id.shp.ee/S3y3YcM"
        },
        "specifications": {
            "platform": "Android",
            "pemasangan": "Ditaruh dimana saja tempat tersembunyi",
            "note": "Akurasi ORIN TAG berbeda dengan GPS Tracker ORIN OBU Series yang memiliki SIM card & terhubung langsung ke GPS satelit. ORIN TAG cocok untuk kebutuhan pelacakan ringan, simpel, dan tanpa repot biaya tambahan. Baterai jika habis bisa beli di supermarket terdekat."
        },
        "is_active": True,
        "sort_order": 7
    },
    {
        "name": "ORIN TAG IOS",
        "sku": "ORIN-TAG-IOS",
        "category": "AKSESORIS",
        "subcategory": "TAG",
        "vehicle_type": "mobil,motor,aset berharga,semua kendaraan",
        "description": "Pelacak mini dengan support bluetooth untuk HP iOS. Compact tracker yang bisa dipasang pada berbagai benda berharga. Termasuk bonus soft case. Tanpa biaya bulanan.",
        "features": {
            "fitur_utama": ["Menunjukan lokasi terakhir", "Ukuran kecil", "Sensor Bunyi Nyaring (under control)", "Tanpa Biaya Bulanan", "Ukuran Mini & Ringan", "Jangkauan Global", "Bonus Soft Case"],
            "kompatibilitas": "iOS",
            "tipe": "Bluetooth/GPS tracker",
            "bonus": "Soft Case (tersedia warna putih, pink, biru, dan hitam)"
        },
        "price": None,
        "installation_type": "pasang_mandiri",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": True,
        "battery_life": "6 bulan",
        "power_source": "Battery (CR2032)",
        "tracking_type": "Bluetooth (bukan GPS satelit)",
        "monthly_fee": None,
        "ecommerce_links": {
            "shopee": "https://id.shp.ee/eAi7vgk"
        },
        "specifications": {
            "platform": "iOS",
            "pemasangan": "Ditaruh dimana saja tempat tersembunyi",
            "note": "Akurasi ORIN TAG berbeda dengan GPS Tracker ORIN OBU Series yang memiliki SIM card & terhubung langsung ke GPS satelit. ORIN TAG cocok untuk kebutuhan pelacakan ringan, simpel, dan tanpa repot biaya tambahan. Baterai jika habis bisa beli di supermarket terdekat."
        },
        "is_active": True,
        "sort_order": 8
    },
    {
        "name": "AI CAM",
        "sku": "AI-CAM",
        "category": "KAMERA",
        "subcategory": "CAMERA",
        "vehicle_type": "mobil,truk,bus",
        "description": "Kamera AI dengan fitur streaming live, deteksi AI (ADAS & DMS), dan GPS tracker.",
        "features": {
            "fitur_utama": ["Streaming Live Camera", "Deteksi AI (ADAS & DMS)", "Pengawasan Audio", "Komunikasi microphone 2 arah", "GPS lacak real-time", "Laporan perjalanan"],
            "tidak_termasuk": "SDCard penyimpanan"
        },
        "price": "600rb/6 bulan atau 1.200.000/tahun (perpanjangan kuota include server)",
        "installation_type": "pasang_technisi",
        "can_shutdown_engine": False,
        "can_wiretap": False,
        "is_realtime_tracking": True,
        "portable": False,
        "battery_life": None,
        "power_source": "Vehicle battery",
        "tracking_type": "GPS Satelit",
        "monthly_fee": "600rb/6 bulan atau 1.200.000/tahun",
        "ecommerce_links": {
            "shopee": "https://id.shp.ee/YXi7N7Z"
        },
        "specifications": {
            "garansi": "1 tahun",
            "note": "Varian 'unit only' hanya alat saja tanpa kuota dan server"
        },
        "is_active": True,
        "sort_order": 9
    }
]
