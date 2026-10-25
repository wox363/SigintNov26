"""
Custom India places — supplement to geonamescache.

geonamescache covers cities with population >= ~15,000. SIGINT cases often
involve smaller villages, towers, and sensitive locations. This file
adds those manually with verified coordinates.

Format: { "name": [lat, lng, "display_label"] }
Lowercase keys for case-insensitive lookup.
"""

INDIA_PLACES = {
    # J&K — Kashmir Valley
    "srinagar": [34.0837, 74.7973, "Srinagar, Jammu & Kashmir, India"],
    "anantnag": [33.7311, 75.1487, "Anantnag, Jammu & Kashmir, India"],
    "baramulla": [34.1986, 74.3636, "Baramulla, Jammu & Kashmir, India"],
    "pulwama": [33.8755, 74.8997, "Pulwama, Jammu & Kashmir, India"],
    "kupwara": [34.5314, 74.2547, "Kupwara, Jammu & Kashmir, India"],
    "bandipora": [34.4172, 74.6483, "Bandipora, Jammu & Kashmir, India"],
    "budgam": [33.9856, 74.7339, "Budgam, Jammu & Kashmir, India"],
    "ganderbal": [34.2236, 74.7758, "Ganderbal, Jammu & Kashmir, India"],
    "shopian": [33.7167, 74.8333, "Shopian, Jammu & Kashmir, India"],
    "kulgam": [33.6447, 75.0192, "Kulgam, Jammu & Kashmir, India"],
    "sopore": [34.2864, 74.4711, "Sopore, Jammu & Kashmir, India"],
    "pahalgam": [34.0167, 75.3167, "Pahalgam, Jammu & Kashmir, India"],
    "gulmarg": [34.0500, 74.3800, "Gulmarg, Jammu & Kashmir, India"],
    "sonmarg": [34.3000, 75.3000, "Sonmarg, Jammu & Kashmir, India"],
    "dudhpatri": [33.9667, 74.6500, "Dudhpatri, Budgam, J&K, India"],
    "yousmarg": [33.8333, 74.6667, "Yousmarg, Budgam, J&K, India"],
    "bemina": [34.0833, 74.7833, "Bemina, Srinagar, J&K, India"],
    "lal chowk": [34.0792, 74.8089, "Lal Chowk, Srinagar, J&K, India"],
    "nowgam": [34.0639, 74.7806, "Nowgam, Srinagar, J&K, India"],
    "sumbal": [34.2333, 74.6500, "Sumbal, Bandipora, J&K, India"],
    "wangipora": [34.0167, 74.8167, "Wangipora, Pulwama, J&K, India"],
    "hazratbal": [34.1417, 74.8389, "Hazratbal, Srinagar, J&K, India"],
    "dal lake": [34.1167, 74.8500, "Dal Lake, Srinagar, J&K, India"],
    "tral": [33.9333, 75.1167, "Tral, Pulwama, J&K, India"],
    "awantipora": [33.9167, 75.0167, "Awantipora, Pulwama, J&K, India"],
    "bijbehara": [33.7950, 75.1031, "Bijbehara, Anantnag, J&K, India"],
    "achabal": [33.7167, 75.2167, "Achabal, Anantnag, J&K, India"],
    "verinag": [33.5333, 75.2667, "Verinag, Anantnag, J&K, India"],
    "kokernag": [33.6167, 75.3167, "Kokernag, Anantnag, J&K, India"],
    "uri": [34.0833, 74.0500, "Uri, Baramulla, J&K, India"],
    "tangmarg": [34.0500, 74.4333, "Tangmarg, Baramulla, J&K, India"],
    "handwara": [34.4000, 74.2833, "Handwara, Kupwara, J&K, India"],
    "kreeri": [34.2667, 74.5000, "Kreeri, Baramulla, J&K, India"],
    "pampore": [34.0167, 74.9333, "Pampore, Pulwama, J&K, India"],
    "qazigund": [33.6333, 75.1500, "Qazigund, Anantnag, J&K, India"],
    "banihal": [33.4333, 75.2000, "Banihal, Ramban, J&K, India"],
    "arampora": [34.1500, 74.7833, "Arampora, J&K, India"],

    # J&K — Jammu region
    "jammu": [32.7266, 74.8570, "Jammu, J&K, India"],
    "udhampur": [32.9159, 75.1417, "Udhampur, J&K, India"],
    "doda": [33.1456, 75.5469, "Doda, J&K, India"],
    "kishtwar": [33.3128, 75.7681, "Kishtwar, J&K, India"],
    "rajouri": [33.3753, 74.3128, "Rajouri, J&K, India"],
    "poonch": [33.7708, 74.0958, "Poonch, J&K, India"],
    "kathua": [32.3697, 75.5181, "Kathua, J&K, India"],
    "samba": [32.5611, 75.1186, "Samba, J&K, India"],
    "reasi": [33.0817, 74.8367, "Reasi, J&K, India"],
    "ramban": [33.2422, 75.2419, "Ramban, J&K, India"],

    # Border / sensitive
    "loc": [34.2000, 74.0000, "Line of Control (approx), J&K"],
    "line of control": [34.2000, 74.0000, "Line of Control (approx), J&K"],
    "wagah": [31.6047, 74.5731, "Wagah Border, Punjab, India"],
    "attari": [31.6017, 74.6075, "Attari, Punjab, India"],

    # Punjab
    "amritsar": [31.6340, 74.8723, "Amritsar, Punjab, India"],
    "ludhiana": [30.9010, 75.8573, "Ludhiana, Punjab, India"],
    "jalandhar": [31.3260, 75.5762, "Jalandhar, Punjab, India"],
    "chandigarh": [30.7333, 76.7794, "Chandigarh, India"],
    "patiala": [30.3398, 76.3869, "Patiala, Punjab, India"],
    "bathinda": [30.2110, 74.9455, "Bathinda, Punjab, India"],
    "mohali": [30.7046, 76.7179, "Mohali, Punjab, India"],
    "pathankot": [32.2746, 75.6526, "Pathankot, Punjab, India"],
    "ferozepur": [30.9322, 74.6225, "Ferozepur, Punjab, India"],
    "gurdaspur": [32.0411, 75.4053, "Gurdaspur, Punjab, India"],
}
