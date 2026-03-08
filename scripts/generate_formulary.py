#!/usr/bin/env python3
"""Generate comprehensive South African formulary JSON with 500+ drugs."""
import json
import os

drugs = []
code = 1

def add(name, aliases, strengths, route, category, schedule):
    global code
    drugs.append({
        "code": f"{code:04d}",
        "name": name,
        "aliases": aliases,
        "strengths": strengths,
        "defaultRoute": route,
        "category": category,
        "scheduleClass": schedule
    })
    code += 1

# ============================================================
# ANTIBIOTICS — Penicillins
# ============================================================
add("Amoxicillin", ["amoxil","amoxicillin","amoxycillin","amox"], ["250mg","500mg","125mg/5ml"], "PO", "antibiotic", "S4")
add("Amoxicillin-Clavulanate", ["augmentin","co-amoxiclav","amoxiclav"], ["375mg","625mg","228mg/5ml"], "PO", "antibiotic", "S4")
add("Ampicillin", ["ampicillin","penbritin"], ["250mg","500mg","1g"], "PO", "antibiotic", "S4")
add("Flucloxacillin", ["flucloxacillin","floxapen","fluclox"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Phenoxymethylpenicillin", ["penicillin v","penicillin vk","pen v","pen-vk"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Benzylpenicillin", ["penicillin g","penilevel","crystapen"], ["1MU","5MU"], "IV", "antibiotic", "S4")
add("Benzathine Benzylpenicillin", ["bicillin","penilente-la","benzathine penicillin"], ["1.2MU","2.4MU"], "IM", "antibiotic", "S4")
add("Procaine Benzylpenicillin", ["procaine penicillin"], ["1MU","3MU"], "IM", "antibiotic", "S4")
add("Piperacillin-Tazobactam", ["tazocin","pip-tazo","piptaz"], ["4.5g"], "IV", "antibiotic", "S4")
add("Cloxacillin", ["cloxacillin","orbenin"], ["250mg","500mg"], "PO", "antibiotic", "S4")

# Cephalosporins
add("Cephalexin", ["cephalexin","cefalexin","keflex"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Cefazolin", ["cefazolin","cephazolin","kefzol"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefuroxime", ["cefuroxime","zinacef","zinnat"], ["250mg","500mg","750mg"], "PO", "antibiotic", "S4")
add("Ceftriaxone", ["ceftriaxone","rocephin"], ["250mg","1g","2g"], "IV", "antibiotic", "S4")
add("Ceftazidime", ["ceftazidime","fortum"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefixime", ["cefixime","suprax"], ["200mg","400mg"], "PO", "antibiotic", "S4")
add("Cefotaxime", ["cefotaxime","claforan"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefepime", ["cefepime","maxipime"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefpodoxime", ["cefpodoxime","orelox"], ["100mg","200mg"], "PO", "antibiotic", "S4")

# Macrolides
add("Azithromycin", ["azithromycin","zithromax","azithro","zmax"], ["250mg","500mg","200mg/5ml"], "PO", "antibiotic", "S4")
add("Erythromycin", ["erythromycin","eryc","erythrocin","ery-tab"], ["250mg","500mg","125mg/5ml"], "PO", "antibiotic", "S4")
add("Clarithromycin", ["clarithromycin","klacid","biaxin"], ["250mg","500mg"], "PO", "antibiotic", "S4")

# Fluoroquinolones
add("Ciprofloxacin", ["ciprofloxacin","cipro","ciproxin"], ["250mg","500mg","750mg"], "PO", "antibiotic", "S4")
add("Levofloxacin", ["levofloxacin","tavanic","levaquin"], ["250mg","500mg","750mg"], "PO", "antibiotic", "S4")
add("Moxifloxacin", ["moxifloxacin","avelox","moxiflox"], ["400mg"], "PO", "antibiotic", "S4")
add("Ofloxacin", ["ofloxacin","tarivid"], ["200mg","400mg"], "PO", "antibiotic", "S4")
add("Norfloxacin", ["norfloxacin","noroxin"], ["400mg"], "PO", "antibiotic", "S4")
add("Nalidixic Acid", ["nalidixic acid","negram"], ["500mg"], "PO", "antibiotic", "S4")

# Tetracyclines
add("Doxycycline", ["doxycycline","vibramycin","doxymycin","doxy"], ["100mg","50mg"], "PO", "antibiotic", "S4")
add("Tetracycline", ["tetracycline","achromycin"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Minocycline", ["minocycline","minocin"], ["50mg","100mg"], "PO", "antibiotic", "S4")
add("Tigecycline", ["tigecycline","tygacil"], ["50mg"], "IV", "antibiotic", "S4")

# Aminoglycosides
add("Gentamicin", ["gentamicin","garamycin","gentamycin"], ["80mg/2ml","40mg/ml"], "IV", "antibiotic", "S4")
add("Amikacin", ["amikacin","amiklin"], ["250mg/ml","500mg/2ml"], "IV", "antibiotic", "S4")
add("Tobramycin", ["tobramycin","nebcin"], ["80mg/2ml"], "IV", "antibiotic", "S4")
add("Kanamycin", ["kanamycin","kantrex"], ["1g"], "IM", "antibiotic", "S4")
add("Streptomycin", ["streptomycin"], ["1g"], "IM", "antibiotic", "S4")

# Sulfonamides / Nitroimidazoles
add("Cotrimoxazole", ["cotrimoxazole","bactrim","septran","tmp-smx","co-trimoxazole","sulfamethoxazole-trimethoprim"], ["480mg","960mg","240mg/5ml"], "PO", "antibiotic", "S4")
add("Trimethoprim", ["trimethoprim","triprim"], ["100mg","200mg"], "PO", "antibiotic", "S4")
add("Sulfadiazine", ["sulfadiazine","sulphadiazine"], ["500mg"], "PO", "antibiotic", "S4")
add("Metronidazole", ["metronidazole","flagyl","metro"], ["200mg","400mg","500mg/100ml"], "PO", "antibiotic", "S4")
add("Tinidazole", ["tinidazole","fasigyn"], ["500mg"], "PO", "antibiotic", "S4")
add("Secnidazole", ["secnidazole"], ["500mg","1g"], "PO", "antibiotic", "S4")

# Carbapenems / Other
add("Meropenem", ["meropenem","merrem"], ["500mg","1g"], "IV", "antibiotic", "S4")
add("Imipenem-Cilastatin", ["imipenem","tienam","primaxin"], ["500mg"], "IV", "antibiotic", "S4")
add("Ertapenem", ["ertapenem","invanz"], ["1g"], "IV", "antibiotic", "S4")
add("Vancomycin", ["vancomycin","vancocin"], ["500mg","1g"], "IV", "antibiotic", "S4")
add("Teicoplanin", ["teicoplanin","targocid"], ["200mg","400mg"], "IV", "antibiotic", "S4")
add("Linezolid", ["linezolid","zyvox"], ["600mg"], "PO", "antibiotic", "S4")
add("Clindamycin", ["clindamycin","dalacin","dalacin-c"], ["150mg","300mg","600mg"], "PO", "antibiotic", "S4")
add("Chloramphenicol", ["chloramphenicol","chloromycetin"], ["250mg","1g"], "PO", "antibiotic", "S4")
add("Nitrofurantoin", ["nitrofurantoin","macrodantin","macrobid"], ["50mg","100mg"], "PO", "antibiotic", "S4")
add("Fosfomycin", ["fosfomycin","monurol"], ["3g"], "PO", "antibiotic", "S4")
add("Colistin", ["colistin","colistimethate","colomycin"], ["1MU","2MU"], "IV", "antibiotic", "S4")
add("Fusidic Acid", ["fusidic acid","fucidin"], ["250mg"], "PO", "antibiotic", "S4")
add("Mupirocin", ["mupirocin","bactroban"], ["2% ointment"], "TOP", "antibiotic", "S4")

# ============================================================
# ANTITUBERCULAR
# ============================================================
add("Isoniazid", ["isoniazid","inh","rimifon"], ["100mg","300mg"], "PO", "antitubercular", "S4")
add("Rifampicin", ["rifampicin","rifampin","rimactane","rifadin"], ["150mg","300mg","600mg"], "PO", "antitubercular", "S4")
add("Pyrazinamide", ["pyrazinamide","pza"], ["500mg"], "PO", "antitubercular", "S4")
add("Ethambutol", ["ethambutol","myambutol","emb"], ["400mg"], "PO", "antitubercular", "S4")
add("Rifafour", ["rifafour","4fdc","rhze"], ["150/75/400/275mg"], "PO", "antitubercular", "S4")
add("Rifinah", ["rifinah","rh","2fdc"], ["150/75mg","300/150mg"], "PO", "antitubercular", "S4")
add("Bedaquiline", ["bedaquiline","sirturo"], ["100mg"], "PO", "antitubercular", "S4")
add("Delamanid", ["delamanid","deltyba"], ["50mg"], "PO", "antitubercular", "S4")
add("Pretomanid", ["pretomanid"], ["200mg"], "PO", "antitubercular", "S4")
add("Linezolid", ["linezolid","zyvox"], ["600mg"], "PO", "antitubercular", "S4")
add("Levofloxacin", ["levofloxacin","tavanic"], ["250mg","500mg","750mg"], "PO", "antitubercular", "S4")
add("Cycloserine", ["cycloserine","seromycin"], ["250mg"], "PO", "antitubercular", "S4")
add("Ethionamide", ["ethionamide","trecator"], ["250mg"], "PO", "antitubercular", "S4")
add("Para-aminosalicylic Acid", ["pas","paser","para-aminosalicylic acid"], ["4g"], "PO", "antitubercular", "S4")
add("Clofazimine", ["clofazimine","lamprene"], ["50mg","100mg"], "PO", "antitubercular", "S4")

# ============================================================
# ANTIMALARIALS
# ============================================================
add("Artemether-Lumefantrine", ["coartem","artemether-lumefantrine","al"], ["20/120mg"], "PO", "antimalarial", "S4")
add("Quinine", ["quinine","quinine sulfate","quinine sulphate"], ["300mg","600mg/2ml"], "PO", "antimalarial", "S4")
add("Mefloquine", ["mefloquine","lariam"], ["250mg"], "PO", "antimalarial", "S4")
add("Doxycycline", ["doxycycline"], ["100mg"], "PO", "antimalarial", "S4")
add("Atovaquone-Proguanil", ["malarone","atovaquone-proguanil"], ["250/100mg"], "PO", "antimalarial", "S4")
add("Chloroquine", ["chloroquine","plaquenil","nivaquine"], ["150mg"], "PO", "antimalarial", "S4")
add("Primaquine", ["primaquine"], ["7.5mg","15mg"], "PO", "antimalarial", "S4")
add("Artesunate", ["artesunate"], ["60mg","120mg"], "IV", "antimalarial", "S4")
add("Sulfadoxine-Pyrimethamine", ["fansidar","sp"], ["500/25mg"], "PO", "antimalarial", "S4")
add("Proguanil", ["proguanil","paludrine"], ["100mg"], "PO", "antimalarial", "S4")

# ============================================================
# ANTIRETROVIRALS
# ============================================================
add("Tenofovir Disoproxil Fumarate", ["tenofovir","tdf","viread"], ["300mg"], "PO", "antiretroviral", "S4")
add("Tenofovir Alafenamide", ["tenofovir alafenamide","taf"], ["25mg"], "PO", "antiretroviral", "S4")
add("Emtricitabine", ["emtricitabine","ftc","emtriva"], ["200mg"], "PO", "antiretroviral", "S4")
add("Lamivudine", ["lamivudine","3tc","epivir"], ["150mg","300mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("Dolutegravir", ["dolutegravir","dtg","tivicay"], ["50mg","10mg"], "PO", "antiretroviral", "S4")
add("Efavirenz", ["efavirenz","efv","stocrin","sustiva"], ["200mg","600mg"], "PO", "antiretroviral", "S4")
add("Zidovudine", ["zidovudine","azt","retrovir"], ["100mg","300mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("Abacavir", ["abacavir","abc","ziagen"], ["300mg","600mg","20mg/ml"], "PO", "antiretroviral", "S4")
add("Nevirapine", ["nevirapine","nvp","viramune"], ["200mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("Lopinavir-Ritonavir", ["aluvia","kaletra","lpv/r"], ["200/50mg","80/20mg/ml"], "PO", "antiretroviral", "S4")
add("Atazanavir", ["atazanavir","atv","reyataz"], ["300mg"], "PO", "antiretroviral", "S4")
add("Atazanavir-Ritonavir", ["atazanavir/ritonavir","atv/r"], ["300/100mg"], "PO", "antiretroviral", "S4")
add("Ritonavir", ["ritonavir","rtv","norvir"], ["100mg","80mg/ml"], "PO", "antiretroviral", "S4")
add("Darunavir", ["darunavir","drv","prezista"], ["400mg","600mg","800mg"], "PO", "antiretroviral", "S4")
add("Raltegravir", ["raltegravir","ral","isentress"], ["400mg"], "PO", "antiretroviral", "S4")
add("Tenofovir-Emtricitabine", ["truvada","tdf/ftc"], ["300/200mg"], "PO", "antiretroviral", "S4")
add("Tenofovir-Lamivudine-Dolutegravir", ["tld","tdf/3tc/dtg"], ["300/300/50mg"], "PO", "antiretroviral", "S4")
add("Tenofovir-Emtricitabine-Efavirenz", ["atripla","tdf/ftc/efv"], ["300/200/600mg"], "PO", "antiretroviral", "S4")
add("Abacavir-Lamivudine", ["kivexa","abc/3tc"], ["600/300mg"], "PO", "antiretroviral", "S4")
add("Zidovudine-Lamivudine", ["combivir","azt/3tc"], ["300/150mg"], "PO", "antiretroviral", "S4")
add("Zidovudine-Lamivudine-Nevirapine", ["azt/3tc/nvp","fixed dose combination"], ["300/150/200mg"], "PO", "antiretroviral", "S4")
add("Etravirine", ["etravirine","etr","intelence"], ["100mg","200mg"], "PO", "antiretroviral", "S4")
add("Maraviroc", ["maraviroc","mvc","celsentri"], ["150mg","300mg"], "PO", "antiretroviral", "S4")
add("Cabotegravir", ["cabotegravir","cab","vocabria"], ["30mg","600mg/3ml"], "PO", "antiretroviral", "S4")
add("Lenacapavir", ["lenacapavir","sunlenca"], ["300mg","927mg/1.5ml"], "PO", "antiretroviral", "S4")

# ============================================================
# ANTIFUNGALS
# ============================================================
add("Fluconazole", ["fluconazole","diflucan"], ["50mg","150mg","200mg","2mg/ml"], "PO", "antifungal", "S4")
add("Itraconazole", ["itraconazole","sporanox"], ["100mg"], "PO", "antifungal", "S4")
add("Voriconazole", ["voriconazole","vfend"], ["200mg","50mg"], "PO", "antifungal", "S4")
add("Amphotericin B", ["amphotericin b","amphotericin","fungizone"], ["50mg"], "IV", "antifungal", "S4")
add("Amphotericin B Liposomal", ["ambisome","liposomal amphotericin"], ["50mg"], "IV", "antifungal", "S4")
add("Flucytosine", ["flucytosine","5-fc","ancobon"], ["500mg","2.5g/250ml"], "PO", "antifungal", "S4")
add("Nystatin", ["nystatin","mycostatin"], ["100000IU/ml","500000IU"], "PO", "antifungal", "S2")
add("Clotrimazole", ["clotrimazole","canesten"], ["1% cream","10mg troche","100mg pessary","500mg pessary"], "TOP", "antifungal", "S2")
add("Miconazole", ["miconazole","daktarin"], ["2% cream","2% oral gel"], "TOP", "antifungal", "S2")
add("Ketoconazole", ["ketoconazole","nizoral"], ["200mg","2% cream","2% shampoo"], "PO", "antifungal", "S4")
add("Terbinafine", ["terbinafine","lamisil"], ["250mg","1% cream"], "PO", "antifungal", "S4")
add("Griseofulvin", ["griseofulvin","grisovin","fulcin"], ["125mg","500mg"], "PO", "antifungal", "S4")
add("Caspofungin", ["caspofungin","cancidas"], ["50mg","70mg"], "IV", "antifungal", "S4")
add("Micafungin", ["micafungin","mycamine"], ["50mg","100mg"], "IV", "antifungal", "S4")
add("Econazole", ["econazole","ecostatin","pevaryl"], ["1% cream","150mg pessary"], "TOP", "antifungal", "S2")

# ============================================================
# ANTIPARASITICS / ANTHELMINTHICS
# ============================================================
add("Albendazole", ["albendazole","zentel"], ["200mg","400mg"], "PO", "anthelminthic", "S2")
add("Mebendazole", ["mebendazole","vermox"], ["100mg","500mg"], "PO", "anthelminthic", "S2")
add("Praziquantel", ["praziquantel","biltricide"], ["600mg"], "PO", "anthelminthic", "S4")
add("Ivermectin", ["ivermectin","stromectol"], ["3mg","6mg"], "PO", "antiparasitic", "S4")
add("Pyrantel Pamoate", ["pyrantel","combantrin"], ["125mg","250mg"], "PO", "anthelminthic", "S2")
add("Niclosamide", ["niclosamide","yomesan"], ["500mg"], "PO", "anthelminthic", "S4")
add("Diethylcarbamazine", ["diethylcarbamazine","dec","hetrazan"], ["50mg"], "PO", "antiparasitic", "S4")
add("Pentamidine", ["pentamidine","pentacarinat"], ["200mg","300mg"], "IV", "antiparasitic", "S4")
add("Suramin", ["suramin","germanin"], ["1g"], "IV", "antiparasitic", "S4")
add("Benznidazole", ["benznidazole"], ["100mg"], "PO", "antiparasitic", "S4")
add("Sodium Stibogluconate", ["sodium stibogluconate","pentostam"], ["100mg/ml"], "IV", "antiparasitic", "S4")
add("Permethrin", ["permethrin","lyclear","nix"], ["1% lotion","5% cream"], "TOP", "antiparasitic", "S2")
add("Benzyl Benzoate", ["benzyl benzoate"], ["25% lotion"], "TOP", "antiparasitic", "S2")
add("Gamma Benzene Hexachloride", ["lindane","gbh"], ["1% lotion"], "TOP", "antiparasitic", "S4")
add("Quinine Dihydrochloride", ["quinine dihydrochloride","quinine iv"], ["300mg/ml"], "IV", "antiparasitic", "S4")

# ============================================================
# ANALGESICS & NSAIDs
# ============================================================
add("Paracetamol", ["paracetamol","panado","acetaminophen","tylenol","pacimol"], ["500mg","1g","120mg/5ml","10mg/ml"], "PO", "analgesic", "S0")
add("Ibuprofen", ["ibuprofen","brufen","nurofen","advil"], ["200mg","400mg","600mg","100mg/5ml"], "PO", "NSAID", "S2")
add("Diclofenac", ["diclofenac","voltaren","cataflam"], ["25mg","50mg","75mg","75mg/3ml","1% gel"], "PO", "NSAID", "S3")
add("Naproxen", ["naproxen","naprosyn","aleve"], ["250mg","500mg"], "PO", "NSAID", "S3")
add("Indomethacin", ["indomethacin","indocid","indometacin"], ["25mg","50mg"], "PO", "NSAID", "S4")
add("Celecoxib", ["celecoxib","celebrex"], ["100mg","200mg"], "PO", "NSAID", "S4")
add("Meloxicam", ["meloxicam","mobic"], ["7.5mg","15mg"], "PO", "NSAID", "S3")
add("Piroxicam", ["piroxicam","feldene"], ["10mg","20mg"], "PO", "NSAID", "S3")
add("Aspirin", ["aspirin","disprin","ecotrin","acetylsalicylic acid","asa"], ["75mg","100mg","300mg","500mg"], "PO", "analgesic", "S2")
add("Tramadol", ["tramadol","tramal"], ["50mg","100mg","100mg/ml"], "PO", "opioid analgesic", "S5")
add("Morphine", ["morphine","morphine sulphate","morphine sulfate"], ["10mg","15mg","30mg","10mg/ml"], "PO", "opioid analgesic", "S7")
add("Codeine Phosphate", ["codeine","codeine phosphate"], ["15mg","30mg","60mg"], "PO", "opioid analgesic", "S5")
add("Pethidine", ["pethidine","meperidine","demerol"], ["50mg","100mg","50mg/ml"], "IM", "opioid analgesic", "S6")
add("Fentanyl", ["fentanyl","durogesic","sublimaze"], ["25mcg/hr","50mcg/hr","100mcg/2ml"], "IV", "opioid analgesic", "S7")
add("Oxycodone", ["oxycodone","oxycontin","oxynorm"], ["5mg","10mg","20mg"], "PO", "opioid analgesic", "S7")
add("Naloxone", ["naloxone","narcan"], ["0.4mg/ml","1mg/ml"], "IV", "opioid antagonist", "S4")
add("Dihydrocodeine", ["dihydrocodeine","df118"], ["30mg"], "PO", "opioid analgesic", "S5")
add("Tilidine", ["tilidine","valoron"], ["50mg"], "PO", "opioid analgesic", "S5")
add("Ketamine", ["ketamine","ketalar"], ["50mg/ml","10mg/ml"], "IV", "analgesic", "S5")

# ============================================================
# ANTIDIABETICS
# ============================================================
add("Metformin", ["metformin","glucophage","metfin"], ["500mg","850mg","1000mg"], "PO", "antidiabetic", "S3")
add("Glibenclamide", ["glibenclamide","daonil","glyburide"], ["2.5mg","5mg"], "PO", "antidiabetic", "S3")
add("Gliclazide", ["gliclazide","diamicron"], ["30mg","60mg","80mg"], "PO", "antidiabetic", "S3")
add("Glimepiride", ["glimepiride","amaryl"], ["1mg","2mg","4mg"], "PO", "antidiabetic", "S3")
add("Glipizide", ["glipizide","minidiab"], ["5mg"], "PO", "antidiabetic", "S3")
add("Insulin Soluble", ["actrapid","humulin r","insulin regular","soluble insulin"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Isophane", ["protaphane","humulin n","nph insulin","isophane insulin"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Biphasic", ["mixtard 30","humulin 30/70","novomix 30","biphasic insulin"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Glargine", ["lantus","basaglar","toujeo","insulin glargine"], ["100IU/ml","300IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Aspart", ["novorapid","fiasp","insulin aspart"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Lispro", ["humalog","insulin lispro"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Detemir", ["levemir","insulin detemir"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Degludec", ["tresiba","insulin degludec"], ["100IU/ml","200IU/ml"], "SC", "antidiabetic", "S4")
add("Pioglitazone", ["pioglitazone","actos"], ["15mg","30mg"], "PO", "antidiabetic", "S3")
add("Empagliflozin", ["empagliflozin","jardiance"], ["10mg","25mg"], "PO", "antidiabetic", "S4")
add("Dapagliflozin", ["dapagliflozin","forxiga"], ["5mg","10mg"], "PO", "antidiabetic", "S4")
add("Sitagliptin", ["sitagliptin","januvia"], ["25mg","50mg","100mg"], "PO", "antidiabetic", "S4")
add("Vildagliptin", ["vildagliptin","galvus"], ["50mg"], "PO", "antidiabetic", "S4")
add("Liraglutide", ["liraglutide","victoza","saxenda"], ["6mg/ml"], "SC", "antidiabetic", "S4")
add("Semaglutide", ["semaglutide","ozempic","rybelsus"], ["0.25mg","0.5mg","1mg","7mg","14mg"], "SC", "antidiabetic", "S4")
add("Metformin-Glibenclamide", ["glucovance"], ["500/2.5mg","500/5mg"], "PO", "antidiabetic", "S3")
add("Acarbose", ["acarbose","glucobay"], ["50mg","100mg"], "PO", "antidiabetic", "S3")
add("Tolbutamide", ["tolbutamide","rastinon"], ["500mg"], "PO", "antidiabetic", "S3")

# ============================================================
# ANTIHYPERTENSIVES
# ============================================================
# ACE Inhibitors
add("Enalapril", ["enalapril","renitec","enap"], ["5mg","10mg","20mg"], "PO", "antihypertensive", "S3")
add("Perindopril", ["perindopril","coversyl"], ["4mg","8mg"], "PO", "antihypertensive", "S3")
add("Ramipril", ["ramipril","tritace"], ["1.25mg","2.5mg","5mg","10mg"], "PO", "antihypertensive", "S3")
add("Lisinopril", ["lisinopril","zestril","prinivil"], ["5mg","10mg","20mg"], "PO", "antihypertensive", "S3")
add("Captopril", ["captopril","capoten"], ["12.5mg","25mg","50mg"], "PO", "antihypertensive", "S3")

# ARBs
add("Losartan", ["losartan","cozaar"], ["50mg","100mg"], "PO", "antihypertensive", "S3")
add("Valsartan", ["valsartan","diovan"], ["80mg","160mg","320mg"], "PO", "antihypertensive", "S3")
add("Telmisartan", ["telmisartan","micardis","pritor"], ["40mg","80mg"], "PO", "antihypertensive", "S3")
add("Irbesartan", ["irbesartan","aprovel","co-aprovel"], ["150mg","300mg"], "PO", "antihypertensive", "S3")
add("Candesartan", ["candesartan","atacand"], ["8mg","16mg","32mg"], "PO", "antihypertensive", "S3")
add("Olmesartan", ["olmesartan","olmetec"], ["10mg","20mg","40mg"], "PO", "antihypertensive", "S3")

# CCBs
add("Amlodipine", ["amlodipine","norvasc","amloc"], ["5mg","10mg"], "PO", "antihypertensive", "S3")
add("Nifedipine", ["nifedipine","adalat","procardia"], ["10mg","20mg","30mg","60mg"], "PO", "antihypertensive", "S3")
add("Verapamil", ["verapamil","isoptin"], ["40mg","80mg","120mg","240mg"], "PO", "antihypertensive", "S3")
add("Diltiazem", ["diltiazem","adizem","cardizem"], ["60mg","90mg","120mg","240mg"], "PO", "antihypertensive", "S3")
add("Felodipine", ["felodipine","plendil"], ["2.5mg","5mg","10mg"], "PO", "antihypertensive", "S3")
add("Lercanidipine", ["lercanidipine","zanidip"], ["10mg","20mg"], "PO", "antihypertensive", "S3")
add("Nimodipine", ["nimodipine","nimotop"], ["30mg"], "PO", "antihypertensive", "S4")

# Beta Blockers
add("Atenolol", ["atenolol","tenormin"], ["50mg","100mg"], "PO", "beta-blocker", "S3")
add("Bisoprolol", ["bisoprolol","concor"], ["2.5mg","5mg","10mg"], "PO", "beta-blocker", "S3")
add("Carvedilol", ["carvedilol","dilatrend"], ["3.125mg","6.25mg","12.5mg","25mg"], "PO", "beta-blocker", "S3")
add("Metoprolol", ["metoprolol","lopressor","betaloc"], ["50mg","100mg","200mg"], "PO", "beta-blocker", "S3")
add("Propranolol", ["propranolol","inderal"], ["10mg","40mg","80mg"], "PO", "beta-blocker", "S3")
add("Labetalol", ["labetalol","trandate"], ["100mg","200mg","5mg/ml"], "PO", "beta-blocker", "S4")
add("Nebivolol", ["nebivolol","nebilet"], ["5mg"], "PO", "beta-blocker", "S3")
add("Sotalol", ["sotalol","sotacor"], ["80mg","160mg"], "PO", "beta-blocker", "S3")

# Diuretics
add("Hydrochlorothiazide", ["hydrochlorothiazide","hctz","ridaq"], ["12.5mg","25mg"], "PO", "diuretic", "S3")
add("Furosemide", ["furosemide","frusemide","lasix"], ["40mg","80mg","20mg/2ml"], "PO", "diuretic", "S3")
add("Spironolactone", ["spironolactone","aldactone"], ["25mg","50mg","100mg"], "PO", "diuretic", "S3")
add("Indapamide", ["indapamide","natrilix"], ["1.5mg","2.5mg"], "PO", "diuretic", "S3")
add("Chlorthalidone", ["chlorthalidone","hygroton"], ["12.5mg","25mg"], "PO", "diuretic", "S3")
add("Eplerenone", ["eplerenone","inspra"], ["25mg","50mg"], "PO", "diuretic", "S4")
add("Metolazone", ["metolazone","zaroxolyn"], ["2.5mg","5mg"], "PO", "diuretic", "S4")
add("Amiloride", ["amiloride","midamor"], ["5mg"], "PO", "diuretic", "S3")
add("Mannitol", ["mannitol"], ["10%","20%"], "IV", "diuretic", "S4")
add("Acetazolamide", ["acetazolamide","diamox"], ["250mg"], "PO", "diuretic", "S4")

# Other antihypertensives
add("Hydralazine", ["hydralazine","apresoline"], ["10mg","25mg","20mg/ml"], "PO", "antihypertensive", "S4")
add("Methyldopa", ["methyldopa","aldomet"], ["250mg","500mg"], "PO", "antihypertensive", "S4")
add("Prazosin", ["prazosin","minipress"], ["1mg","2mg","5mg"], "PO", "antihypertensive", "S3")
add("Doxazosin", ["doxazosin","cardura"], ["2mg","4mg"], "PO", "antihypertensive", "S3")
add("Clonidine", ["clonidine","catapres"], ["0.1mg","0.15mg"], "PO", "antihypertensive", "S4")
add("Minoxidil", ["minoxidil","loniten"], ["5mg","10mg"], "PO", "antihypertensive", "S4")
add("Sodium Nitroprusside", ["sodium nitroprusside","nipride"], ["50mg"], "IV", "antihypertensive", "S4")

# ============================================================
# CARDIOVASCULAR
# ============================================================
# Statins
add("Simvastatin", ["simvastatin","zocor"], ["10mg","20mg","40mg"], "PO", "statin", "S3")
add("Atorvastatin", ["atorvastatin","lipitor"], ["10mg","20mg","40mg","80mg"], "PO", "statin", "S3")
add("Rosuvastatin", ["rosuvastatin","crestor"], ["5mg","10mg","20mg","40mg"], "PO", "statin", "S3")
add("Pravastatin", ["pravastatin","pravachol"], ["10mg","20mg","40mg"], "PO", "statin", "S3")
add("Fluvastatin", ["fluvastatin","lescol"], ["20mg","40mg","80mg"], "PO", "statin", "S3")
add("Ezetimibe", ["ezetimibe","ezetrol","zetia"], ["10mg"], "PO", "lipid-lowering", "S3")
add("Fenofibrate", ["fenofibrate","lipanthyl"], ["160mg","200mg","267mg"], "PO", "lipid-lowering", "S3")
add("Gemfibrozil", ["gemfibrozil","lopid"], ["600mg"], "PO", "lipid-lowering", "S3")
add("Bezafibrate", ["bezafibrate","bezalip"], ["200mg","400mg"], "PO", "lipid-lowering", "S3")

# Anticoagulants
add("Warfarin", ["warfarin","coumadin"], ["1mg","2mg","3mg","5mg"], "PO", "anticoagulant", "S4")
add("Heparin Sodium", ["heparin","heparin sodium"], ["5000IU/ml","25000IU/5ml"], "IV", "anticoagulant", "S4")
add("Enoxaparin", ["enoxaparin","clexane","lovenox"], ["20mg","40mg","60mg","80mg","100mg"], "SC", "anticoagulant", "S4")
add("Rivaroxaban", ["rivaroxaban","xarelto"], ["10mg","15mg","20mg"], "PO", "anticoagulant", "S4")
add("Apixaban", ["apixaban","eliquis"], ["2.5mg","5mg"], "PO", "anticoagulant", "S4")
add("Dabigatran", ["dabigatran","pradaxa"], ["75mg","110mg","150mg"], "PO", "anticoagulant", "S4")
add("Fondaparinux", ["fondaparinux","arixtra"], ["2.5mg","7.5mg"], "SC", "anticoagulant", "S4")
add("Protamine Sulfate", ["protamine","protamine sulfate","protamine sulphate"], ["10mg/ml"], "IV", "anticoagulant reversal", "S4")

# Antiplatelets
add("Clopidogrel", ["clopidogrel","plavix"], ["75mg","300mg"], "PO", "antiplatelet", "S4")
add("Ticagrelor", ["ticagrelor","brilinta"], ["60mg","90mg"], "PO", "antiplatelet", "S4")
add("Dipyridamole", ["dipyridamole","persantin"], ["25mg","75mg","200mg"], "PO", "antiplatelet", "S3")

# Antiarrhythmics
add("Amiodarone", ["amiodarone","cordarone"], ["100mg","200mg","150mg/3ml"], "PO", "antiarrhythmic", "S4")
add("Digoxin", ["digoxin","lanoxin"], ["0.0625mg","0.125mg","0.25mg","0.5mg/2ml"], "PO", "cardiac glycoside", "S4")
add("Adenosine", ["adenosine","adenocard"], ["6mg/2ml"], "IV", "antiarrhythmic", "S4")
add("Lidocaine", ["lidocaine","lignocaine","xylocaine"], ["1%","2%","20mg/ml"], "IV", "antiarrhythmic", "S4")
add("Flecainide", ["flecainide","tambocor"], ["50mg","100mg"], "PO", "antiarrhythmic", "S4")

# Heart failure / other CV
add("Isosorbide Dinitrate", ["isdn","isosorbide dinitrate","isordil"], ["5mg","10mg","20mg"], "PO", "antianginal", "S3")
add("Isosorbide Mononitrate", ["ismn","isosorbide mononitrate","imdur"], ["20mg","40mg","60mg"], "PO", "antianginal", "S3")
add("Glyceryl Trinitrate", ["gtn","nitroglycerin","nitrolingual"], ["0.5mg","5mg/ml","0.4mg/spray"], "SL", "antianginal", "S3")
add("Ivabradine", ["ivabradine","procoralan"], ["5mg","7.5mg"], "PO", "cardiac", "S4")
add("Sacubitril-Valsartan", ["entresto","sacubitril/valsartan"], ["24/26mg","49/51mg","97/103mg"], "PO", "cardiac", "S4")
add("Trimetazidine", ["trimetazidine","vastarel"], ["20mg","35mg"], "PO", "antianginal", "S3")
add("Dobutamine", ["dobutamine","dobutrex"], ["250mg/20ml"], "IV", "inotrope", "S4")
add("Dopamine", ["dopamine","intropin"], ["200mg/5ml"], "IV", "inotrope", "S4")
add("Milrinone", ["milrinone","primacor"], ["10mg/10ml"], "IV", "inotrope", "S4")

# ============================================================
# RESPIRATORY
# ============================================================
add("Salbutamol", ["salbutamol","ventolin","asthavent","albuterol"], ["100mcg/puff","2mg","4mg","5mg/ml nebule"], "INH", "bronchodilator", "S3")
add("Ipratropium Bromide", ["ipratropium","atrovent"], ["20mcg/puff","250mcg/ml nebule"], "INH", "bronchodilator", "S3")
add("Salbutamol-Ipratropium", ["combivent","duolin"], ["100/20mcg/puff"], "INH", "bronchodilator", "S3")
add("Tiotropium", ["tiotropium","spiriva"], ["18mcg","2.5mcg/puff"], "INH", "bronchodilator", "S4")
add("Formoterol", ["formoterol","foradil","oxis"], ["12mcg"], "INH", "bronchodilator", "S4")
add("Salmeterol", ["salmeterol","serevent"], ["25mcg","50mcg"], "INH", "bronchodilator", "S4")
add("Beclomethasone", ["beclomethasone","becotide","becloforte","qvar"], ["50mcg","100mcg","200mcg","250mcg"], "INH", "inhaled corticosteroid", "S4")
add("Budesonide", ["budesonide","pulmicort"], ["100mcg","200mcg","400mcg","0.5mg/2ml nebule"], "INH", "inhaled corticosteroid", "S4")
add("Fluticasone Propionate", ["fluticasone","flixotide"], ["50mcg","125mcg","250mcg"], "INH", "inhaled corticosteroid", "S4")
add("Fluticasone-Salmeterol", ["seretide","advair","fluticasone/salmeterol"], ["50/25mcg","125/25mcg","250/25mcg","100/50mcg","250/50mcg","500/50mcg"], "INH", "combination inhaler", "S4")
add("Budesonide-Formoterol", ["symbicort","budesonide/formoterol"], ["80/4.5mcg","160/4.5mcg","200/6mcg","400/12mcg"], "INH", "combination inhaler", "S4")
add("Beclomethasone-Formoterol", ["foster","inuvair"], ["100/6mcg","200/6mcg"], "INH", "combination inhaler", "S4")
add("Fluticasone Furoate-Vilanterol", ["relvar","breo"], ["92/22mcg","184/22mcg"], "INH", "combination inhaler", "S4")
add("Montelukast", ["montelukast","singulair"], ["4mg","5mg","10mg"], "PO", "leukotriene antagonist", "S4")
add("Theophylline", ["theophylline","theo-dur","nuelin"], ["100mg","200mg","300mg"], "PO", "bronchodilator", "S3")
add("Aminophylline", ["aminophylline","phyllocontin"], ["100mg","225mg","250mg/10ml"], "PO", "bronchodilator", "S4")
add("Cromoglycate Sodium", ["sodium cromoglycate","intal"], ["5mg/puff"], "INH", "mast cell stabilizer", "S3")
add("Prednisolone", ["prednisolone","prelone","pediapred"], ["5mg","20mg","40mg","15mg/5ml"], "PO", "corticosteroid", "S4")
add("Prednisone", ["prednisone","deltasone","meticorten"], ["5mg","10mg","20mg","50mg"], "PO", "corticosteroid", "S4")
add("Carbocisteine", ["carbocisteine","mucodyne"], ["250mg","375mg"], "PO", "mucolytic", "S2")
add("Acetylcysteine", ["acetylcysteine","nac","fluimucil","acc"], ["200mg","600mg"], "PO", "mucolytic", "S2")

# ============================================================
# GI DRUGS
# ============================================================
add("Omeprazole", ["omeprazole","losec","altosec"], ["10mg","20mg","40mg"], "PO", "PPI", "S3")
add("Lansoprazole", ["lansoprazole","lanzor","prevacid"], ["15mg","30mg"], "PO", "PPI", "S3")
add("Pantoprazole", ["pantoprazole","pantoloc","protonix"], ["20mg","40mg"], "PO", "PPI", "S3")
add("Esomeprazole", ["esomeprazole","nexium"], ["20mg","40mg"], "PO", "PPI", "S3")
add("Ranitidine", ["ranitidine","zantac"], ["150mg","300mg"], "PO", "H2 blocker", "S2")
add("Cimetidine", ["cimetidine","tagamet"], ["200mg","400mg","800mg"], "PO", "H2 blocker", "S2")
add("Famotidine", ["famotidine","pepcid"], ["20mg","40mg"], "PO", "H2 blocker", "S2")
add("Sucralfate", ["sucralfate","ulsanic"], ["1g"], "PO", "GI protectant", "S3")
add("Aluminium Hydroxide", ["aluminium hydroxide","alu-tab"], ["500mg"], "PO", "antacid", "S0")
add("Magnesium Hydroxide", ["magnesium hydroxide","milk of magnesia"], ["500mg"], "PO", "antacid", "S0")
add("Magnesium Trisilicate", ["magnesium trisilicate","gastro-soothe"], ["500mg","mixture"], "PO", "antacid", "S0")
add("Calcium Carbonate", ["calcium carbonate","tums","gaviscon"], ["500mg","1g"], "PO", "antacid", "S0")
add("Sodium Bicarbonate", ["sodium bicarbonate","bicarb","baking soda"], ["500mg","8.4%"], "PO", "antacid", "S0")
add("Metoclopramide", ["metoclopramide","maxolon"], ["10mg","5mg/ml"], "PO", "antiemetic", "S4")
add("Domperidone", ["domperidone","motilium"], ["10mg","5mg/5ml"], "PO", "antiemetic", "S3")
add("Ondansetron", ["ondansetron","zofran"], ["4mg","8mg","4mg/2ml"], "PO", "antiemetic", "S4")
add("Promethazine", ["promethazine","phenergan"], ["10mg","25mg","25mg/ml"], "PO", "antiemetic", "S3")
add("Prochlorperazine", ["prochlorperazine","stemetil"], ["5mg","12.5mg/ml"], "PO", "antiemetic", "S4")
add("Cyclizine", ["cyclizine","valoid"], ["50mg"], "PO", "antiemetic", "S3")
add("Dexamethasone", ["dexamethasone","decadron"], ["0.5mg","4mg","4mg/ml"], "PO", "corticosteroid", "S4")
add("Loperamide", ["loperamide","imodium"], ["2mg"], "PO", "antidiarrhoeal", "S2")
add("Bismuth Subsalicylate", ["bismuth","pepto-bismol"], ["262mg"], "PO", "antidiarrhoeal", "S0")
add("ORS", ["ors","oral rehydration salts","rehydration salts"], ["sachet"], "PO", "rehydration", "S0")
add("Zinc Sulfate", ["zinc sulfate","zinc sulphate","zinc"], ["20mg"], "PO", "supplement", "S0")
add("Lactulose", ["lactulose","duphalac"], ["10g/15ml"], "PO", "laxative", "S2")
add("Bisacodyl", ["bisacodyl","dulcolax"], ["5mg","10mg supp"], "PO", "laxative", "S2")
add("Senna", ["senna","senokot"], ["7.5mg","15mg"], "PO", "laxative", "S2")
add("Macrogol", ["macrogol","movicol","miralax","polyethylene glycol","peg"], ["13.7g"], "PO", "laxative", "S0")
add("Docusate Sodium", ["docusate","coloxyl","colace"], ["100mg"], "PO", "laxative", "S2")
add("Liquid Paraffin", ["liquid paraffin","mineral oil"], ["liquid"], "PO", "laxative", "S0")
add("Psyllium", ["psyllium","metamucil","ispaghula"], ["3.5g"], "PO", "laxative", "S0")
add("Misoprostol", ["misoprostol","cytotec"], ["200mcg"], "PO", "GI protectant", "S4")
add("Hyoscine Butylbromide", ["hyoscine butylbromide","buscopan"], ["10mg","20mg/ml"], "PO", "antispasmodic", "S2")
add("Dicyclomine", ["dicyclomine","dicycloverine","merbentyl"], ["10mg","20mg"], "PO", "antispasmodic", "S3")
add("Mebeverine", ["mebeverine","duspatalin"], ["135mg","200mg"], "PO", "antispasmodic", "S3")
add("Mesalazine", ["mesalazine","asacol","pentasa","5-asa","mesalamine"], ["400mg","500mg","1g"], "PO", "GI anti-inflammatory", "S4")
add("Sulfasalazine", ["sulfasalazine","salazopyrin","sulphasalazine"], ["500mg"], "PO", "GI anti-inflammatory", "S4")
add("Pancreatin", ["pancreatin","creon","pancrelipase"], ["10000IU","25000IU"], "PO", "enzyme supplement", "S3")
add("Ursodeoxycholic Acid", ["ursodeoxycholic acid","ursodiol","udca","ursofalk"], ["250mg","300mg"], "PO", "hepatic", "S4")

# ============================================================
# PSYCHIATRIC MEDICATIONS
# ============================================================
# SSRIs
add("Fluoxetine", ["fluoxetine","prozac","lilly fluoxetine","nuzak"], ["20mg","40mg"], "PO", "antidepressant", "S5")
add("Sertraline", ["sertraline","zoloft"], ["50mg","100mg"], "PO", "antidepressant", "S5")
add("Citalopram", ["citalopram","cipramil"], ["10mg","20mg","40mg"], "PO", "antidepressant", "S5")
add("Escitalopram", ["escitalopram","cipralex","lexapro"], ["5mg","10mg","20mg"], "PO", "antidepressant", "S5")
add("Paroxetine", ["paroxetine","paxil","aropax"], ["20mg","40mg"], "PO", "antidepressant", "S5")
add("Fluvoxamine", ["fluvoxamine","luvox","faverin"], ["50mg","100mg"], "PO", "antidepressant", "S5")

# SNRIs
add("Venlafaxine", ["venlafaxine","efexor","effexor"], ["37.5mg","75mg","150mg"], "PO", "antidepressant", "S5")
add("Duloxetine", ["duloxetine","cymbalta"], ["30mg","60mg"], "PO", "antidepressant", "S5")
add("Desvenlafaxine", ["desvenlafaxine","pristiq"], ["50mg","100mg"], "PO", "antidepressant", "S5")

# TCAs
add("Amitriptyline", ["amitriptyline","elavil","trepiline"], ["10mg","25mg","50mg"], "PO", "antidepressant", "S5")
add("Imipramine", ["imipramine","tofranil"], ["10mg","25mg"], "PO", "antidepressant", "S5")
add("Clomipramine", ["clomipramine","anafranil"], ["10mg","25mg","50mg"], "PO", "antidepressant", "S5")
add("Nortriptyline", ["nortriptyline","pamelor"], ["10mg","25mg"], "PO", "antidepressant", "S5")
add("Doxepin", ["doxepin","sinequan"], ["25mg","50mg","75mg"], "PO", "antidepressant", "S5")

# Other antidepressants
add("Mirtazapine", ["mirtazapine","remeron"], ["15mg","30mg","45mg"], "PO", "antidepressant", "S5")
add("Bupropion", ["bupropion","wellbutrin","zyban"], ["150mg","300mg"], "PO", "antidepressant", "S5")
add("Trazodone", ["trazodone","molipaxin","desyrel"], ["50mg","100mg","150mg"], "PO", "antidepressant", "S5")
add("Agomelatine", ["agomelatine","valdoxan"], ["25mg"], "PO", "antidepressant", "S5")
add("Vortioxetine", ["vortioxetine","brintellix","trintellix"], ["5mg","10mg","20mg"], "PO", "antidepressant", "S5")

# Antipsychotics
add("Haloperidol", ["haloperidol","serenace","haldol"], ["1.5mg","5mg","5mg/ml"], "PO", "antipsychotic", "S5")
add("Chlorpromazine", ["chlorpromazine","largactil","thorazine"], ["25mg","50mg","100mg","25mg/ml"], "PO", "antipsychotic", "S5")
add("Risperidone", ["risperidone","risperdal"], ["0.5mg","1mg","2mg","3mg","4mg"], "PO", "antipsychotic", "S5")
add("Olanzapine", ["olanzapine","zyprexa"], ["2.5mg","5mg","10mg","20mg"], "PO", "antipsychotic", "S5")
add("Quetiapine", ["quetiapine","seroquel"], ["25mg","100mg","200mg","300mg"], "PO", "antipsychotic", "S5")
add("Aripiprazole", ["aripiprazole","abilify"], ["5mg","10mg","15mg","30mg"], "PO", "antipsychotic", "S5")
add("Clozapine", ["clozapine","clozaril","leponex"], ["25mg","100mg","200mg"], "PO", "antipsychotic", "S5")
add("Ziprasidone", ["ziprasidone","geodon","zeldox"], ["20mg","40mg","60mg","80mg"], "PO", "antipsychotic", "S5")
add("Paliperidone", ["paliperidone","invega"], ["3mg","6mg","9mg"], "PO", "antipsychotic", "S5")
add("Flupentixol", ["flupentixol","fluanxol","flupenthixol"], ["0.5mg","1mg","3mg","20mg/ml"], "PO", "antipsychotic", "S5")
add("Zuclopenthixol", ["zuclopenthixol","clopixol"], ["10mg","25mg","200mg/ml","50mg/ml"], "PO", "antipsychotic", "S5")
add("Sulpiride", ["sulpiride","eglonyl"], ["200mg","400mg"], "PO", "antipsychotic", "S5")
add("Amisulpride", ["amisulpride","solian"], ["100mg","200mg","400mg"], "PO", "antipsychotic", "S5")
add("Fluphenazine Decanoate", ["fluphenazine","modecate"], ["25mg/ml"], "IM", "antipsychotic", "S5")

# Anxiolytics / Sedatives
add("Diazepam", ["diazepam","valium"], ["2mg","5mg","10mg","5mg/ml"], "PO", "anxiolytic", "S5")
add("Lorazepam", ["lorazepam","ativan"], ["0.5mg","1mg","2mg","4mg/ml"], "PO", "anxiolytic", "S5")
add("Alprazolam", ["alprazolam","xanax"], ["0.25mg","0.5mg","1mg"], "PO", "anxiolytic", "S5")
add("Bromazepam", ["bromazepam","lexotan"], ["1.5mg","3mg","6mg"], "PO", "anxiolytic", "S5")
add("Clonazepam", ["clonazepam","rivotril"], ["0.5mg","1mg","2mg"], "PO", "anxiolytic", "S5")
add("Midazolam", ["midazolam","dormicum"], ["7.5mg","15mg","5mg/ml"], "PO", "sedative", "S5")
add("Buspirone", ["buspirone","buspar"], ["5mg","10mg"], "PO", "anxiolytic", "S5")
add("Hydroxyzine", ["hydroxyzine","atarax"], ["10mg","25mg"], "PO", "anxiolytic", "S4")

# Mood stabilizers
add("Lithium Carbonate", ["lithium","camcolit","priadel"], ["250mg","400mg"], "PO", "mood stabilizer", "S5")
add("Sodium Valproate", ["sodium valproate","epilim","valproic acid","depakote","depakene"], ["200mg","500mg","200mg/5ml"], "PO", "mood stabilizer", "S5")
add("Carbamazepine", ["carbamazepine","tegretol"], ["100mg","200mg","400mg","100mg/5ml"], "PO", "mood stabilizer", "S5")
add("Lamotrigine", ["lamotrigine","lamictin","lamictal"], ["25mg","50mg","100mg","200mg"], "PO", "mood stabilizer", "S5")

# Hypnotics
add("Zolpidem", ["zolpidem","stilnox","ambien"], ["5mg","10mg"], "PO", "hypnotic", "S5")
add("Zopiclone", ["zopiclone","imovane"], ["7.5mg"], "PO", "hypnotic", "S5")

# ADHD
add("Methylphenidate", ["methylphenidate","ritalin","concerta"], ["10mg","18mg","20mg","36mg","54mg"], "PO", "stimulant", "S6")
add("Atomoxetine", ["atomoxetine","strattera"], ["10mg","18mg","25mg","40mg","60mg"], "PO", "ADHD", "S5")

# ============================================================
# NEUROLOGICAL
# ============================================================
# Antiepileptics
add("Phenytoin", ["phenytoin","epanutin","dilantin"], ["100mg","50mg/ml"], "PO", "antiepileptic", "S4")
add("Phenobarbital", ["phenobarbital","phenobarbitone","luminal"], ["30mg","60mg","200mg/ml"], "PO", "antiepileptic", "S5")
add("Valproic Acid", ["valproic acid","epilim","depakene","convulex"], ["200mg","500mg","200mg/5ml"], "PO", "antiepileptic", "S5")
add("Levetiracetam", ["levetiracetam","keppra"], ["250mg","500mg","750mg","1000mg","100mg/ml"], "PO", "antiepileptic", "S4")
add("Topiramate", ["topiramate","topamax"], ["25mg","50mg","100mg","200mg"], "PO", "antiepileptic", "S4")
add("Gabapentin", ["gabapentin","neurontin"], ["100mg","300mg","400mg","600mg","800mg"], "PO", "antiepileptic", "S4")
add("Pregabalin", ["pregabalin","lyrica"], ["25mg","50mg","75mg","150mg","300mg"], "PO", "antiepileptic", "S4")
add("Oxcarbazepine", ["oxcarbazepine","trileptal"], ["150mg","300mg","600mg"], "PO", "antiepileptic", "S4")
add("Ethosuximide", ["ethosuximide","zarontin"], ["250mg"], "PO", "antiepileptic", "S4")
add("Vigabatrin", ["vigabatrin","sabril"], ["500mg"], "PO", "antiepileptic", "S4")
add("Clobazam", ["clobazam","frisium","urbanyl"], ["10mg","20mg"], "PO", "antiepileptic", "S5")
add("Lacosamide", ["lacosamide","vimpat"], ["50mg","100mg","150mg","200mg"], "PO", "antiepileptic", "S4")
add("Brivaracetam", ["brivaracetam","briviact"], ["25mg","50mg","75mg","100mg"], "PO", "antiepileptic", "S4")

# Anti-parkinsonian
add("Levodopa-Carbidopa", ["sinemet","levodopa/carbidopa","carbidopa/levodopa","madopar"], ["100/25mg","250/25mg","100/10mg"], "PO", "anti-parkinsonian", "S4")
add("Trihexyphenidyl", ["trihexyphenidyl","artane","benzhexol"], ["2mg","5mg"], "PO", "anti-parkinsonian", "S4")
add("Biperiden", ["biperiden","akineton"], ["2mg","5mg/ml"], "PO", "anti-parkinsonian", "S4")
add("Pramipexole", ["pramipexole","sifrol","mirapex"], ["0.125mg","0.25mg","0.5mg","1mg"], "PO", "anti-parkinsonian", "S4")
add("Ropinirole", ["ropinirole","requip"], ["0.25mg","0.5mg","1mg","2mg"], "PO", "anti-parkinsonian", "S4")
add("Entacapone", ["entacapone","comtan"], ["200mg"], "PO", "anti-parkinsonian", "S4")
add("Rasagiline", ["rasagiline","azilect"], ["0.5mg","1mg"], "PO", "anti-parkinsonian", "S4")
add("Amantadine", ["amantadine","symmetrel"], ["100mg"], "PO", "anti-parkinsonian", "S4")
add("Orphenadrine", ["orphenadrine","disipal","norflex"], ["50mg","100mg"], "PO", "anti-parkinsonian", "S4")

# Migraine
add("Sumatriptan", ["sumatriptan","imigran","imitrex"], ["50mg","100mg","6mg/0.5ml"], "PO", "antimigraine", "S3")
add("Ergotamine", ["ergotamine","cafergot"], ["1mg"], "PO", "antimigraine", "S4")
add("Flunarizine", ["flunarizine","sibelium"], ["5mg","10mg"], "PO", "antimigraine", "S3")
add("Pizotifen", ["pizotifen","sandomigran"], ["0.5mg","1.5mg"], "PO", "antimigraine", "S3")

# Other neuro
add("Baclofen", ["baclofen","lioresal"], ["10mg","25mg"], "PO", "muscle relaxant", "S4")
add("Donepezil", ["donepezil","aricept"], ["5mg","10mg"], "PO", "anti-dementia", "S4")
add("Memantine", ["memantine","ebixa","namenda"], ["5mg","10mg","20mg"], "PO", "anti-dementia", "S4")
add("Riluzole", ["riluzole","rilutek"], ["50mg"], "PO", "neuroprotective", "S4")

# ============================================================
# CORTICOSTEROIDS
# ============================================================
add("Hydrocortisone", ["hydrocortisone","cortisol","solu-cortef"], ["10mg","20mg","100mg","250mg","500mg"], "PO", "corticosteroid", "S4")
add("Methylprednisolone", ["methylprednisolone","solu-medrol","medrol","depo-medrol"], ["4mg","16mg","40mg","125mg","500mg","1g"], "PO", "corticosteroid", "S4")
add("Betamethasone", ["betamethasone","celestone"], ["0.5mg","4mg/ml"], "PO", "corticosteroid", "S4")
add("Triamcinolone", ["triamcinolone","kenalog","kenacort"], ["4mg","40mg/ml","10mg/ml"], "IM", "corticosteroid", "S4")
add("Fludrocortisone", ["fludrocortisone","florinef"], ["0.1mg"], "PO", "corticosteroid", "S4")
add("Deflazacort", ["deflazacort","calcort"], ["6mg","30mg"], "PO", "corticosteroid", "S4")
add("Hydrocortisone Cream", ["hydrocortisone cream","cortisone cream"], ["0.5%","1%"], "TOP", "topical corticosteroid", "S2")
add("Betamethasone Valerate", ["betamethasone valerate","betnovate","celestoderm"], ["0.02%","0.1%"], "TOP", "topical corticosteroid", "S4")
add("Clobetasol Propionate", ["clobetasol","dermovate"], ["0.05%"], "TOP", "topical corticosteroid", "S4")
add("Mometasone Furoate", ["mometasone","elocon"], ["0.1%"], "TOP", "topical corticosteroid", "S4")
add("Fluocinolone Acetonide", ["fluocinolone","synalar"], ["0.025%"], "TOP", "topical corticosteroid", "S4")

# ============================================================
# ANTIHISTAMINES
# ============================================================
add("Chlorpheniramine", ["chlorpheniramine","piriton","chlorphenamine"], ["4mg","2mg/5ml"], "PO", "antihistamine", "S2")
add("Cetirizine", ["cetirizine","zyrtec"], ["10mg","5mg/5ml"], "PO", "antihistamine", "S2")
add("Loratadine", ["loratadine","clarityne","claritin"], ["10mg","5mg/5ml"], "PO", "antihistamine", "S2")
add("Fexofenadine", ["fexofenadine","telfast","allegra"], ["60mg","120mg","180mg"], "PO", "antihistamine", "S2")
add("Desloratadine", ["desloratadine","aerius","clarinex"], ["5mg"], "PO", "antihistamine", "S2")
add("Levocetirizine", ["levocetirizine","xyzal"], ["5mg"], "PO", "antihistamine", "S2")
add("Promethazine", ["promethazine","phenergan","avomine"], ["10mg","25mg","25mg/ml"], "PO", "antihistamine", "S3")
add("Clemastine", ["clemastine","tavegil"], ["1mg"], "PO", "antihistamine", "S2")
add("Diphenhydramine", ["diphenhydramine","benadryl"], ["25mg","50mg"], "PO", "antihistamine", "S2")

# ============================================================
# VITAMINS & MINERALS
# ============================================================
add("Ferrous Sulfate", ["ferrous sulfate","ferrous sulphate","iron","feso4"], ["200mg","325mg","60mg/5ml"], "PO", "supplement", "S0")
add("Ferrous Fumarate", ["ferrous fumarate","iron fumarate"], ["200mg"], "PO", "supplement", "S0")
add("Iron Sucrose", ["iron sucrose","venofer"], ["100mg/5ml"], "IV", "supplement", "S4")
add("Ferric Carboxymaltose", ["ferric carboxymaltose","ferinject"], ["500mg/10ml"], "IV", "supplement", "S4")
add("Folic Acid", ["folic acid","folate"], ["1mg","5mg"], "PO", "supplement", "S0")
add("Vitamin B12", ["cyanocobalamin","vitamin b12","hydroxocobalamin"], ["1mg/ml","250mcg"], "IM", "supplement", "S2")
add("Vitamin B Complex", ["vitamin b complex","b-complex","neurobion"], ["tablet"], "PO", "supplement", "S0")
add("Thiamine", ["thiamine","vitamin b1","benerva"], ["50mg","100mg","100mg/ml"], "PO", "supplement", "S2")
add("Pyridoxine", ["pyridoxine","vitamin b6"], ["25mg","50mg"], "PO", "supplement", "S2")
add("Niacin", ["niacin","nicotinic acid","vitamin b3"], ["50mg","100mg","500mg"], "PO", "supplement", "S2")
add("Ascorbic Acid", ["ascorbic acid","vitamin c"], ["100mg","250mg","500mg","1000mg"], "PO", "supplement", "S0")
add("Vitamin D3", ["cholecalciferol","vitamin d3","vitamin d","calciferol"], ["400IU","1000IU","50000IU"], "PO", "supplement", "S0")
add("Calcium Carbonate", ["calcium carbonate","caltrate","calci-tab","oscal"], ["500mg","600mg","1250mg"], "PO", "supplement", "S0")
add("Calcium Gluconate", ["calcium gluconate"], ["1g","10%"], "IV", "supplement", "S4")
add("Magnesium Sulfate", ["magnesium sulfate","magnesium sulphate","mgso4","epsom salt"], ["1g/2ml","5g/10ml","50%"], "IV", "supplement", "S4")
add("Magnesium Glycinate", ["magnesium glycinate","magnesium"], ["200mg","400mg"], "PO", "supplement", "S0")
add("Potassium Chloride", ["potassium chloride","kcl","slow-k","kay-cee-l"], ["600mg","8mmol/ml"], "PO", "supplement", "S2")
add("Vitamin A", ["retinol","vitamin a"], ["50000IU","100000IU","200000IU"], "PO", "supplement", "S2")
add("Vitamin E", ["vitamin e","tocopherol","alpha-tocopherol"], ["100IU","200IU","400IU"], "PO", "supplement", "S0")
add("Vitamin K1", ["phytomenadione","phytonadione","vitamin k1","konakion"], ["1mg","10mg/ml"], "PO", "supplement", "S4")
add("Multivitamin", ["multivitamin","multivit"], ["tablet","syrup"], "PO", "supplement", "S0")

# ============================================================
# DERMATOLOGICAL
# ============================================================
add("Aqueous Cream", ["aqueous cream","emollient cream"], ["cream"], "TOP", "dermatological", "S0")
add("Emulsifying Ointment", ["emulsifying ointment"], ["ointment"], "TOP", "dermatological", "S0")
add("Petroleum Jelly", ["petroleum jelly","vaseline","white soft paraffin"], ["ointment"], "TOP", "dermatological", "S0")
add("Calamine Lotion", ["calamine lotion","calamine"], ["lotion"], "TOP", "dermatological", "S0")
add("Zinc Oxide Cream", ["zinc oxide cream","zinc cream","sudocrem"], ["cream"], "TOP", "dermatological", "S0")
add("Silver Sulfadiazine", ["silver sulfadiazine","silver sulphadiazine","flamazine","silvadene"], ["1% cream"], "TOP", "dermatological", "S4")
add("Povidone-Iodine", ["povidone-iodine","betadine"], ["5%","10%"], "TOP", "antiseptic", "S0")
add("Chlorhexidine", ["chlorhexidine","hibitane","savlon"], ["0.05%","0.5%","4%"], "TOP", "antiseptic", "S0")
add("Benzoyl Peroxide", ["benzoyl peroxide","benzac","brevoxyl"], ["2.5%","5%","10%"], "TOP", "dermatological", "S2")
add("Tretinoin", ["tretinoin","retinoic acid","retin-a"], ["0.025%","0.05%"], "TOP", "dermatological", "S4")
add("Adapalene", ["adapalene","differin"], ["0.1%","0.3%"], "TOP", "dermatological", "S4")
add("Isotretinoin", ["isotretinoin","roaccutane","accutane"], ["10mg","20mg","40mg"], "PO", "dermatological", "S4")
add("Coal Tar", ["coal tar","polytar"], ["solution","shampoo"], "TOP", "dermatological", "S2")
add("Salicylic Acid", ["salicylic acid"], ["2%","5%","10%"], "TOP", "dermatological", "S2")
add("Urea Cream", ["urea cream"], ["10%","20%"], "TOP", "dermatological", "S0")
add("Dithranol", ["dithranol","anthralin"], ["0.1%","0.5%","1%"], "TOP", "dermatological", "S4")
add("Calcipotriol", ["calcipotriol","daivonex","dovonex"], ["0.005%"], "TOP", "dermatological", "S4")
add("Tacrolimus Ointment", ["tacrolimus ointment","protopic"], ["0.03%","0.1%"], "TOP", "dermatological", "S4")
add("Pimecrolimus", ["pimecrolimus","elidel"], ["1%"], "TOP", "dermatological", "S4")
add("Podophyllotoxin", ["podophyllotoxin","condyline","wartec"], ["0.5%"], "TOP", "dermatological", "S4")
add("Aciclovir Cream", ["aciclovir cream","acyclovir cream","zovirax cream"], ["5% cream"], "TOP", "antiviral topical", "S2")

# ============================================================
# OPHTHALMOLOGICAL
# ============================================================
add("Chloramphenicol Eye Drops", ["chloramphenicol eye drops","chloromycetin eye drops"], ["0.5%"], "OPH", "ophthalmic antibiotic", "S4")
add("Chloramphenicol Eye Ointment", ["chloramphenicol eye ointment"], ["1%"], "OPH", "ophthalmic antibiotic", "S4")
add("Ciprofloxacin Eye Drops", ["ciprofloxacin eye drops","ciloxan"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Ofloxacin Eye Drops", ["ofloxacin eye drops","exocin"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Tobramycin Eye Drops", ["tobramycin eye drops","tobrex"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Gentamicin Eye Drops", ["gentamicin eye drops","garamycin ophthalmic"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Erythromycin Eye Ointment", ["erythromycin eye ointment"], ["0.5%"], "OPH", "ophthalmic antibiotic", "S4")
add("Fusidic Acid Eye Drops", ["fusidic acid eye drops","fucithalmic"], ["1%"], "OPH", "ophthalmic antibiotic", "S4")
add("Tetracycline Eye Ointment", ["tetracycline eye ointment"], ["1%"], "OPH", "ophthalmic antibiotic", "S4")
add("Timolol Eye Drops", ["timolol eye drops","timoptol"], ["0.25%","0.5%"], "OPH", "anti-glaucoma", "S4")
add("Latanoprost Eye Drops", ["latanoprost","xalatan"], ["0.005%"], "OPH", "anti-glaucoma", "S4")
add("Pilocarpine Eye Drops", ["pilocarpine eye drops","isopto carpine"], ["1%","2%","4%"], "OPH", "anti-glaucoma", "S4")
add("Brimonidine Eye Drops", ["brimonidine","alphagan"], ["0.15%","0.2%"], "OPH", "anti-glaucoma", "S4")
add("Dorzolamide Eye Drops", ["dorzolamide","trusopt"], ["2%"], "OPH", "anti-glaucoma", "S4")
add("Travoprost Eye Drops", ["travoprost","travatan"], ["0.004%"], "OPH", "anti-glaucoma", "S4")
add("Atropine Eye Drops", ["atropine eye drops","isopto atropine"], ["0.5%","1%"], "OPH", "mydriatic", "S4")
add("Tropicamide Eye Drops", ["tropicamide","mydriacyl"], ["0.5%","1%"], "OPH", "mydriatic", "S4")
add("Phenylephrine Eye Drops", ["phenylephrine eye drops"], ["2.5%","10%"], "OPH", "mydriatic", "S4")
add("Dexamethasone Eye Drops", ["dexamethasone eye drops","maxidex"], ["0.1%"], "OPH", "ophthalmic corticosteroid", "S4")
add("Prednisolone Eye Drops", ["prednisolone eye drops","pred forte"], ["0.12%","1%"], "OPH", "ophthalmic corticosteroid", "S4")
add("Fluorometholone Eye Drops", ["fluorometholone","fml"], ["0.1%"], "OPH", "ophthalmic corticosteroid", "S4")
add("Sodium Cromoglycate Eye Drops", ["sodium cromoglycate eye drops","opticrom"], ["2%"], "OPH", "ophthalmic anti-allergy", "S2")
add("Artificial Tears", ["artificial tears","tears naturale","hypromellose","celluvisc"], ["0.3%","0.5%"], "OPH", "ophthalmic lubricant", "S0")
add("Fluorescein Eye Drops", ["fluorescein","fluorescein sodium"], ["1%","2%"], "OPH", "diagnostic", "S4")

# ============================================================
# ENT PREPARATIONS
# ============================================================
add("Oxymetazoline Nasal Spray", ["oxymetazoline","drixine","iliadin","afrin"], ["0.025%","0.05%"], "NAS", "nasal decongestant", "S2")
add("Xylometazoline Nasal Spray", ["xylometazoline","otrivin","sinutab nasal"], ["0.05%","0.1%"], "NAS", "nasal decongestant", "S2")
add("Beclomethasone Nasal Spray", ["beclomethasone nasal","beconase"], ["50mcg/spray"], "NAS", "nasal corticosteroid", "S4")
add("Fluticasone Nasal Spray", ["fluticasone nasal","flixonase","avamys"], ["50mcg/spray","27.5mcg/spray"], "NAS", "nasal corticosteroid", "S4")
add("Mometasone Nasal Spray", ["mometasone nasal","nasonex"], ["50mcg/spray"], "NAS", "nasal corticosteroid", "S4")
add("Budesonide Nasal Spray", ["budesonide nasal","rhinocort"], ["64mcg/spray","100mcg/spray"], "NAS", "nasal corticosteroid", "S4")
add("Saline Nasal Spray", ["saline nasal","normal saline nasal","sterimar"], ["0.9%"], "NAS", "nasal irrigation", "S0")
add("Ciprofloxacin Ear Drops", ["ciprofloxacin ear drops","cipro hc otic"], ["0.3%"], "OT", "otic antibiotic", "S4")
add("Ofloxacin Ear Drops", ["ofloxacin ear drops"], ["0.3%"], "OT", "otic antibiotic", "S4")
add("Neomycin-Polymyxin Ear Drops", ["sofradex","neomycin ear drops"], ["ear drops"], "OT", "otic antibiotic", "S4")
add("Acetic Acid Ear Drops", ["acetic acid ear drops","earcalm"], ["2%"], "OT", "otic", "S2")
add("Hydrogen Peroxide Ear Drops", ["hydrogen peroxide ear drops"], ["3%"], "OT", "otic", "S0")
add("Pseudoephedrine", ["pseudoephedrine","sudafed","sinutab"], ["30mg","60mg"], "PO", "decongestant", "S2")

# ============================================================
# OBSTETRIC / GYNECOLOGICAL
# ============================================================
add("Oxytocin", ["oxytocin","syntocinon","pitocin"], ["5IU/ml","10IU/ml"], "IV", "oxytocic", "S4")
add("Ergometrine", ["ergometrine","ergonovine","ergotrate"], ["0.2mg","0.5mg/ml"], "IM", "oxytocic", "S4")
add("Misoprostol", ["misoprostol","cytotec"], ["200mcg"], "PO", "oxytocic", "S4")
add("Magnesium Sulfate", ["magnesium sulfate","mgso4"], ["50%","5g/10ml"], "IV", "eclampsia treatment", "S4")
add("Nifedipine", ["nifedipine","adalat"], ["10mg","30mg"], "PO", "tocolytic", "S3")
add("Atosiban", ["atosiban","tractocile"], ["7.5mg/ml"], "IV", "tocolytic", "S4")
add("Tranexamic Acid", ["tranexamic acid","cyklokapron","lysteda"], ["250mg","500mg","100mg/ml"], "PO", "antifibrinolytic", "S4")
add("Carbetocin", ["carbetocin","duratocin"], ["100mcg/ml"], "IV", "oxytocic", "S4")
add("Dinoprostone", ["dinoprostone","prostin e2","cervidil"], ["1mg","2mg","10mg"], "VAG", "prostaglandin", "S4")
add("Mifepristone", ["mifepristone","ru-486"], ["200mg"], "PO", "antiprogestogen", "S4")
add("Clomifene", ["clomifene","clomiphene","clomid","serophene"], ["50mg"], "PO", "fertility", "S4")
add("Progesterone", ["progesterone","utrogestan","prometrium"], ["100mg","200mg","400mg"], "PO", "hormone", "S4")

# ============================================================
# HORMONAL / CONTRACEPTIVES
# ============================================================
add("Levonorgestrel", ["levonorgestrel","plan b","norlevo","escapelle"], ["0.75mg","1.5mg"], "PO", "emergency contraceptive", "S3")
add("Ethinylestradiol-Levonorgestrel", ["nordette","triphasil","ovral","microgynon","rigevidon"], ["30/150mcg","50/250mcg"], "PO", "combined oral contraceptive", "S3")
add("Ethinylestradiol-Norethisterone", ["brevinor","norinyl","ortho-novum"], ["35mcg/1mg","35mcg/0.5mg"], "PO", "combined oral contraceptive", "S3")
add("Ethinylestradiol-Gestodene", ["femoden","gynera","minulet"], ["30/75mcg","20/75mcg"], "PO", "combined oral contraceptive", "S3")
add("Ethinylestradiol-Drospirenone", ["yasmin","yaz"], ["30/3mg","20/3mg"], "PO", "combined oral contraceptive", "S3")
add("Ethinylestradiol-Desogestrel", ["marvelon","mercilon"], ["30/150mcg","20/150mcg"], "PO", "combined oral contraceptive", "S3")
add("Norethisterone", ["norethisterone","primolut-n","norethindrone"], ["5mg"], "PO", "progestogen", "S4")
add("Medroxyprogesterone", ["medroxyprogesterone","depo-provera","provera","petogen","nur-isterate"], ["5mg","10mg","150mg/ml"], "PO", "progestogen", "S4")
add("Etonogestrel Implant", ["implanon","nexplanon","etonogestrel implant"], ["68mg"], "SC", "contraceptive implant", "S4")
add("Levonorgestrel IUD", ["mirena","kyleena","levonorgestrel iud","lng-ius"], ["52mg","19.5mg"], "VAG", "intrauterine contraceptive", "S4")
add("Copper IUD", ["copper iud","copper t","paragard","cu-iud"], ["device"], "VAG", "intrauterine contraceptive", "unscheduled")
add("Desogestrel", ["desogestrel","cerazette"], ["75mcg"], "PO", "progestogen-only pill", "S3")
add("Conjugated Estrogens", ["conjugated estrogens","premarin"], ["0.3mg","0.625mg","1.25mg"], "PO", "hormone replacement", "S4")
add("Estradiol Valerate", ["estradiol valerate","progynova"], ["1mg","2mg"], "PO", "hormone replacement", "S4")
add("Tibolone", ["tibolone","livial"], ["2.5mg"], "PO", "hormone replacement", "S4")
add("Testosterone", ["testosterone","sustanon","depo-testosterone","nebido"], ["250mg/ml"], "IM", "androgen", "S5")

# Thyroid
add("Levothyroxine", ["levothyroxine","eltroxin","euthyrox","synthroid","thyroxine"], ["25mcg","50mcg","100mcg","150mcg","200mcg"], "PO", "thyroid hormone", "S4")
add("Carbimazole", ["carbimazole","neo-mercazole"], ["5mg","10mg","20mg"], "PO", "antithyroid", "S4")
add("Propylthiouracil", ["propylthiouracil","ptu"], ["50mg","100mg"], "PO", "antithyroid", "S4")
add("Lugol's Iodine", ["lugol iodine","potassium iodide"], ["5%"], "PO", "thyroid", "S4")

# ============================================================
# VACCINES
# ============================================================
add("BCG Vaccine", ["bcg","bacillus calmette-guerin"], ["0.05ml"], "ID", "vaccine", "S4")
add("OPV", ["opv","oral polio vaccine","sabin"], ["dose"], "PO", "vaccine", "S4")
add("IPV", ["ipv","inactivated polio vaccine","salk"], ["0.5ml"], "IM", "vaccine", "S4")
add("Hepatitis B Vaccine", ["hepatitis b vaccine","engerix-b","hepb"], ["0.5ml","1ml"], "IM", "vaccine", "S4")
add("DTaP-IPV-Hib-HepB Vaccine", ["hexavalent vaccine","hexaxim","infanrix hexa"], ["0.5ml"], "IM", "vaccine", "S4")
add("Measles Vaccine", ["measles vaccine","measles-rubella","mr vaccine"], ["0.5ml"], "SC", "vaccine", "S4")
add("MMR Vaccine", ["mmr","priorix","measles mumps rubella"], ["0.5ml"], "SC", "vaccine", "S4")
add("PCV13 Vaccine", ["pcv13","prevenar 13","pneumococcal conjugate"], ["0.5ml"], "IM", "vaccine", "S4")
add("PPV23 Vaccine", ["ppv23","pneumovax 23","pneumococcal polysaccharide"], ["0.5ml"], "IM", "vaccine", "S4")
add("Rotavirus Vaccine", ["rotavirus vaccine","rotarix","rotateq"], ["1.5ml"], "PO", "vaccine", "S4")
add("HPV Vaccine", ["hpv vaccine","gardasil","cervarix"], ["0.5ml"], "IM", "vaccine", "S4")
add("Influenza Vaccine", ["flu vaccine","influenza vaccine","vaxigrip","fluarix"], ["0.5ml"], "IM", "vaccine", "S4")
add("Tetanus Toxoid Vaccine", ["tetanus toxoid","tt","tetanus vaccine"], ["0.5ml"], "IM", "vaccine", "S4")
add("Td Vaccine", ["td vaccine","tetanus-diphtheria"], ["0.5ml"], "IM", "vaccine", "S4")
add("Typhoid Vaccine", ["typhoid vaccine","typhim vi","vivotif"], ["0.5ml"], "IM", "vaccine", "S4")
add("Hepatitis A Vaccine", ["hepatitis a vaccine","havrix","vaqta"], ["0.5ml","1ml"], "IM", "vaccine", "S4")
add("Rabies Vaccine", ["rabies vaccine","verorab","rabipur"], ["0.5ml","1ml"], "IM", "vaccine", "S4")
add("Yellow Fever Vaccine", ["yellow fever vaccine","stamaril"], ["0.5ml"], "SC", "vaccine", "S4")
add("Meningococcal Vaccine", ["meningococcal vaccine","menactra","nimenrix","menveo"], ["0.5ml"], "IM", "vaccine", "S4")
add("Varicella Vaccine", ["varicella vaccine","varilrix","varivax","chickenpox vaccine"], ["0.5ml"], "SC", "vaccine", "S4")
add("COVID-19 Vaccine", ["covid vaccine","comirnaty","pfizer covid","covid-19 vaccine"], ["0.3ml"], "IM", "vaccine", "S4")

# ============================================================
# EMERGENCY DRUGS
# ============================================================
add("Adrenaline", ["adrenaline","epinephrine","epipen"], ["1mg/ml","0.5mg/ml"], "IM", "emergency", "S4")
add("Atropine", ["atropine","atropine sulfate","atropine sulphate"], ["0.5mg/ml","1mg/ml"], "IV", "emergency", "S4")
add("Sodium Bicarbonate", ["sodium bicarbonate","nahco3","bicarb"], ["8.4%","4.2%"], "IV", "emergency", "S4")
add("Calcium Gluconate", ["calcium gluconate","cal-g"], ["10%","10ml"], "IV", "emergency", "S4")
add("Dextrose", ["dextrose","glucose","d50w","dextrose 50%"], ["50%","10%","5%"], "IV", "emergency", "S4")
add("Normal Saline", ["normal saline","nacl 0.9%","sodium chloride 0.9%"], ["0.9%"], "IV", "fluid", "S0")
add("Ringer's Lactate", ["ringers lactate","hartmanns","lactated ringers"], ["1000ml"], "IV", "fluid", "S0")
add("Gelatin Solution", ["gelofusine","haemaccel","gelatin"], ["4%","500ml"], "IV", "colloid", "S4")
add("Hydrocortisone Injection", ["hydrocortisone injection","solu-cortef"], ["100mg","250mg","500mg"], "IV", "emergency corticosteroid", "S4")
add("Diazepam Rectal", ["diazepam rectal","stesolid","diazemuls"], ["5mg/2.5ml","10mg/2ml"], "PR", "emergency", "S5")
add("Phenytoin Injection", ["phenytoin injection","epanutin injection"], ["250mg/5ml"], "IV", "emergency", "S4")
add("Furosemide Injection", ["furosemide injection","lasix injection"], ["20mg/2ml","40mg/4ml"], "IV", "emergency", "S3")
add("Aminophylline Injection", ["aminophylline injection"], ["250mg/10ml"], "IV", "emergency", "S4")
add("Activated Charcoal", ["activated charcoal","charcodote","ultracarbon"], ["50g"], "PO", "antidote", "S0")
add("Ipecacuanha", ["ipecac","ipecacuanha","syrup of ipecac"], ["15ml","30ml"], "PO", "emetic", "S4")
add("N-Acetylcysteine IV", ["nac iv","acetylcysteine iv","parvolex"], ["200mg/ml"], "IV", "antidote", "S4")
add("Glucagon", ["glucagon","glucagen"], ["1mg"], "IM", "emergency", "S4")
add("Pralidoxime", ["pralidoxime","protopam","2-pam"], ["1g"], "IV", "antidote", "S4")
add("Desferrioxamine", ["desferrioxamine","deferoxamine","desferal"], ["500mg","2g"], "IV", "antidote", "S4")
add("Flumazenil", ["flumazenil","anexate"], ["0.5mg/5ml"], "IV", "antidote", "S4")

# ============================================================
# LOCAL ANAESTHETICS
# ============================================================
add("Lidocaine", ["lidocaine","lignocaine","xylocaine"], ["1%","2%","1% with adrenaline","2% with adrenaline"], "SC", "local anaesthetic", "S4")
add("Bupivacaine", ["bupivacaine","marcaine"], ["0.25%","0.5%","0.5% with adrenaline"], "SC", "local anaesthetic", "S4")
add("Ropivacaine", ["ropivacaine","naropin"], ["0.2%","0.5%","0.75%"], "SC", "local anaesthetic", "S4")
add("Prilocaine", ["prilocaine","citanest"], ["1%","2%","3%"], "SC", "local anaesthetic", "S4")
add("Lidocaine-Prilocaine", ["emla","emla cream","lidocaine-prilocaine cream"], ["2.5%/2.5%"], "TOP", "topical anaesthetic", "S4")
add("Benzocaine", ["benzocaine","anbesol","orajel"], ["7.5%","10%","20%"], "TOP", "topical anaesthetic", "S2")
add("Tetracaine", ["tetracaine","amethocaine","ametop"], ["4% gel","1%"], "TOP", "topical anaesthetic", "S4")

# General / IV anaesthetics
add("Propofol", ["propofol","diprivan"], ["10mg/ml","20mg/ml"], "IV", "general anaesthetic", "S5")
add("Thiopental", ["thiopental","thiopentone","pentothal"], ["500mg","1g"], "IV", "general anaesthetic", "S5")
add("Etomidate", ["etomidate","amidate"], ["2mg/ml"], "IV", "general anaesthetic", "S5")
add("Succinylcholine", ["succinylcholine","suxamethonium","scoline","anectine"], ["100mg/2ml"], "IV", "neuromuscular blocker", "S4")
add("Rocuronium", ["rocuronium","esmeron"], ["10mg/ml"], "IV", "neuromuscular blocker", "S4")
add("Atracurium", ["atracurium","tracrium"], ["10mg/ml"], "IV", "neuromuscular blocker", "S4")
add("Neostigmine", ["neostigmine","prostigmin"], ["0.5mg/ml","2.5mg/ml"], "IV", "anticholinesterase", "S4")

# ============================================================
# MUSCULOSKELETAL
# ============================================================
add("Allopurinol", ["allopurinol","zyloprim","zyloric"], ["100mg","300mg"], "PO", "antigout", "S3")
add("Colchicine", ["colchicine","colcine"], ["0.5mg","1mg"], "PO", "antigout", "S4")
add("Probenecid", ["probenecid","benemid"], ["500mg"], "PO", "antigout", "S4")
add("Febuxostat", ["febuxostat","adenuric","uloric"], ["40mg","80mg","120mg"], "PO", "antigout", "S4")
add("Tizanidine", ["tizanidine","sirdalud","zanaflex"], ["2mg","4mg"], "PO", "muscle relaxant", "S4")
add("Methocarbamol", ["methocarbamol","robaxin"], ["500mg","750mg"], "PO", "muscle relaxant", "S3")
add("Cyclobenzaprine", ["cyclobenzaprine","flexeril"], ["5mg","10mg"], "PO", "muscle relaxant", "S4")
add("Dantrolene", ["dantrolene","dantrium"], ["25mg","50mg","100mg","20mg"], "PO", "muscle relaxant", "S4")
add("Chlorzoxazone", ["chlorzoxazone","parafon forte"], ["250mg","500mg"], "PO", "muscle relaxant", "S3")
add("Methotrexate", ["methotrexate","mtx","trexall"], ["2.5mg","10mg","15mg/ml","25mg/ml"], "PO", "DMARD", "S4")
add("Sulfasalazine", ["sulfasalazine","salazopyrin","sulphasalazine"], ["500mg"], "PO", "DMARD", "S4")
add("Hydroxychloroquine", ["hydroxychloroquine","plaquenil"], ["200mg"], "PO", "DMARD", "S4")
add("Leflunomide", ["leflunomide","arava"], ["10mg","20mg"], "PO", "DMARD", "S4")
add("Calcium + Vitamin D", ["calcium vitamin d","caltrate plus d","calciferol-d"], ["500mg/400IU","600mg/400IU"], "PO", "bone supplement", "S0")
add("Alendronate", ["alendronate","fosamax","alendronic acid"], ["10mg","70mg"], "PO", "bisphosphonate", "S4")
add("Zoledronic Acid", ["zoledronic acid","aclasta","zometa"], ["4mg","5mg"], "IV", "bisphosphonate", "S4")
add("Ibandronate", ["ibandronate","bonviva","boniva"], ["150mg","3mg/3ml"], "PO", "bisphosphonate", "S4")
add("Risedronate", ["risedronate","actonel"], ["5mg","35mg"], "PO", "bisphosphonate", "S4")
add("Strontium Ranelate", ["strontium ranelate","protelos"], ["2g"], "PO", "bone", "S4")
add("Teriparatide", ["teriparatide","forteo"], ["250mcg/ml"], "SC", "bone anabolic", "S4")
add("Denosumab", ["denosumab","prolia","xgeva"], ["60mg","120mg"], "SC", "bone", "S4")

# ============================================================
# UROLOGICAL
# ============================================================
add("Tamsulosin", ["tamsulosin","omnic","flomax"], ["0.4mg"], "PO", "urological", "S3")
add("Alfuzosin", ["alfuzosin","xatral","uroxatral"], ["10mg"], "PO", "urological", "S3")
add("Finasteride", ["finasteride","proscar","propecia"], ["1mg","5mg"], "PO", "urological", "S4")
add("Dutasteride", ["dutasteride","avodart"], ["0.5mg"], "PO", "urological", "S4")
add("Oxybutynin", ["oxybutynin","ditropan","lyrinel"], ["2.5mg","5mg"], "PO", "urological", "S3")
add("Solifenacin", ["solifenacin","vesicare"], ["5mg","10mg"], "PO", "urological", "S3")
add("Tolterodine", ["tolterodine","detrusitol"], ["1mg","2mg","4mg"], "PO", "urological", "S3")
add("Mirabegron", ["mirabegron","betmiga","myrbetriq"], ["25mg","50mg"], "PO", "urological", "S3")
add("Sildenafil", ["sildenafil","viagra","revatio"], ["25mg","50mg","100mg","20mg"], "PO", "PDE5 inhibitor", "S4")
add("Tadalafil", ["tadalafil","cialis","adcirca"], ["5mg","10mg","20mg"], "PO", "PDE5 inhibitor", "S4")
add("Potassium Citrate", ["potassium citrate","uralyt-u"], ["1080mg","granules"], "PO", "urological", "S2")

# ============================================================
# IMMUNOSUPPRESSANTS
# ============================================================
add("Ciclosporin", ["ciclosporin","cyclosporine","sandimmune","neoral"], ["25mg","50mg","100mg"], "PO", "immunosuppressant", "S4")
add("Tacrolimus", ["tacrolimus","prograf","advagraf"], ["0.5mg","1mg","5mg"], "PO", "immunosuppressant", "S4")
add("Azathioprine", ["azathioprine","imuran"], ["50mg"], "PO", "immunosuppressant", "S4")
add("Mycophenolate Mofetil", ["mycophenolate","cellcept","mmf"], ["250mg","500mg"], "PO", "immunosuppressant", "S4")
add("Sirolimus", ["sirolimus","rapamune"], ["1mg","2mg"], "PO", "immunosuppressant", "S4")
add("Everolimus", ["everolimus","certican","afinitor"], ["0.25mg","0.5mg","0.75mg"], "PO", "immunosuppressant", "S4")
add("Basiliximab", ["basiliximab","simulect"], ["20mg"], "IV", "immunosuppressant", "S4")

# ============================================================
# ANTIVIRAL (NON-ARV)
# ============================================================
add("Aciclovir", ["aciclovir","acyclovir","zovirax"], ["200mg","400mg","800mg","250mg"], "PO", "antiviral", "S4")
add("Valaciclovir", ["valaciclovir","valacyclovir","valtrex"], ["500mg","1g"], "PO", "antiviral", "S4")
add("Ganciclovir", ["ganciclovir","cymevene","cytovene"], ["250mg","500mg"], "IV", "antiviral", "S4")
add("Valganciclovir", ["valganciclovir","valcyte"], ["450mg"], "PO", "antiviral", "S4")
add("Oseltamivir", ["oseltamivir","tamiflu"], ["30mg","45mg","75mg"], "PO", "antiviral", "S4")
add("Ribavirin", ["ribavirin","rebetol","copegus"], ["200mg","400mg"], "PO", "antiviral", "S4")
add("Sofosbuvir", ["sofosbuvir","sovaldi"], ["400mg"], "PO", "antiviral", "S4")
add("Sofosbuvir-Ledipasvir", ["harvoni","sofosbuvir/ledipasvir"], ["400/90mg"], "PO", "antiviral", "S4")
add("Sofosbuvir-Velpatasvir", ["epclusa","sofosbuvir/velpatasvir"], ["400/100mg"], "PO", "antiviral", "S4")
add("Glecaprevir-Pibrentasvir", ["maviret","glecaprevir/pibrentasvir"], ["100/40mg"], "PO", "antiviral", "S4")

# ============================================================
# ONCOLOGY SUPPORTIVE / COMMON
# ============================================================
add("Tamoxifen", ["tamoxifen","nolvadex"], ["10mg","20mg"], "PO", "antineoplastic", "S4")
add("Anastrozole", ["anastrozole","arimidex"], ["1mg"], "PO", "antineoplastic", "S4")
add("Letrozole", ["letrozole","femara"], ["2.5mg"], "PO", "antineoplastic", "S4")
add("Cyclophosphamide", ["cyclophosphamide","endoxan","cytoxan"], ["50mg","200mg","500mg","1g"], "PO", "antineoplastic", "S4")
add("Methotrexate Injection", ["methotrexate injection","mtx injection"], ["50mg/2ml"], "IM", "antineoplastic", "S4")
add("Hydroxyurea", ["hydroxyurea","hydroxycarbamide","hydrea"], ["500mg"], "PO", "antineoplastic", "S4")
add("Imatinib", ["imatinib","gleevec","glivec"], ["100mg","400mg"], "PO", "antineoplastic", "S4")
add("Filgrastim", ["filgrastim","neupogen","g-csf"], ["300mcg","480mcg"], "SC", "colony stimulating factor", "S4")
add("Mesna", ["mesna","uromitexan"], ["200mg","400mg","1g"], "IV", "cytoprotectant", "S4")
add("Granisetron", ["granisetron","kytril"], ["1mg","3mg/3ml"], "PO", "antiemetic", "S4")
add("Aprepitant", ["aprepitant","emend"], ["80mg","125mg"], "PO", "antiemetic", "S4")

# ============================================================
# MISCELLANEOUS
# ============================================================
add("Dapsone", ["dapsone"], ["25mg","50mg","100mg"], "PO", "anti-leprosy", "S4")
add("Rifampicin", ["rifampicin","rifadin"], ["150mg","300mg"], "PO", "anti-leprosy", "S4")
add("Clofazimine", ["clofazimine","lamprene"], ["50mg","100mg"], "PO", "anti-leprosy", "S4")
add("Sodium Valproate Syrup", ["epilim syrup","valproate syrup"], ["200mg/5ml"], "PO", "antiepileptic", "S5")
add("Loperamide", ["loperamide","imodium","lopamide"], ["2mg"], "PO", "antidiarrhoeal", "S2")
add("Domperidone Suspension", ["domperidone suspension","motilium suspension"], ["5mg/5ml"], "PO", "antiemetic", "S3")
add("Nystatin Oral Suspension", ["nystatin oral","mycostatin oral"], ["100000IU/ml"], "PO", "antifungal", "S2")
add("Metformin XR", ["metformin xr","glucophage xr","metformin extended release"], ["500mg","750mg","1000mg"], "PO", "antidiabetic", "S3")
add("Enalapril-Hydrochlorothiazide", ["co-renitec","enalapril/hctz"], ["20/12.5mg"], "PO", "antihypertensive", "S3")
add("Losartan-Hydrochlorothiazide", ["hyzaar","losartan/hctz","co-losartan"], ["50/12.5mg","100/25mg"], "PO", "antihypertensive", "S3")
add("Amlodipine-Valsartan", ["exforge","amlodipine/valsartan"], ["5/80mg","5/160mg","10/160mg"], "PO", "antihypertensive", "S3")
add("Perindopril-Amlodipine", ["coveram","perindopril/amlodipine"], ["5/5mg","5/10mg","10/5mg","10/10mg"], "PO", "antihypertensive", "S3")
add("Amlodipine-Atenolol", ["amlopress-at","amlodipine/atenolol"], ["5/50mg"], "PO", "antihypertensive", "S3")
add("Sitagliptin-Metformin", ["janumet","sitagliptin/metformin"], ["50/500mg","50/1000mg"], "PO", "antidiabetic", "S4")
add("Empagliflozin-Metformin", ["jardiance met","empagliflozin/metformin"], ["5/500mg","5/1000mg","12.5/500mg","12.5/1000mg"], "PO", "antidiabetic", "S4")
add("Atorvastatin-Ezetimibe", ["atozet","atorvastatin/ezetimibe"], ["10/10mg","20/10mg","40/10mg"], "PO", "lipid-lowering", "S3")
add("Aspirin-Clopidogrel", ["coplavix","duoplavin","aspirin/clopidogrel"], ["75/75mg","100/75mg"], "PO", "antiplatelet", "S4")
add("Doxylamine-Pyridoxine", ["xonvea","diclegis","doxylamine/pyridoxine"], ["10/10mg"], "PO", "antiemetic", "S3")
add("Spironolactone", ["spironolactone","aldactone"], ["25mg","50mg","100mg"], "PO", "antiandrogen", "S3")
add("Cyproterone Acetate", ["cyproterone","androcur","diane-35"], ["2mg","50mg","100mg"], "PO", "antiandrogen", "S4")
add("Calcitonin", ["calcitonin","miacalcic"], ["100IU","200IU"], "NAS", "bone", "S4")
add("Octreotide", ["octreotide","sandostatin"], ["0.1mg/ml","0.5mg/ml"], "SC", "hormone", "S4")
add("Vasopressin", ["vasopressin","pitressin"], ["20IU/ml"], "IV", "vasopressor", "S4")
add("Noradrenaline", ["noradrenaline","norepinephrine","levophed"], ["1mg/ml","4mg/4ml"], "IV", "vasopressor", "S4")
add("Phenylephrine", ["phenylephrine","neosynephrine"], ["10mg/ml"], "IV", "vasopressor", "S4")
add("Isoprenaline", ["isoprenaline","isoproterenol","isuprel"], ["1mg/5ml"], "IV", "cardiac stimulant", "S4")
add("Nitrous Oxide", ["nitrous oxide","entonox","n2o"], ["50/50 mix"], "INH", "analgesic gas", "S4")
add("Oxygen", ["oxygen","o2","medical oxygen"], ["cylinder","concentrator"], "INH", "medical gas", "S0")
add("Water for Injection", ["water for injection","wfi","sterile water"], ["5ml","10ml","20ml"], "IV", "solvent", "S0")
add("Sodium Chloride 0.45%", ["half normal saline","nacl 0.45%","0.45% saline"], ["500ml","1000ml"], "IV", "fluid", "S0")
add("Dextrose 5%", ["dextrose 5%","d5w","5% dextrose"], ["500ml","1000ml"], "IV", "fluid", "S0")
add("Dextrose-Saline", ["dextrose-saline","d5ns","dns"], ["500ml","1000ml"], "IV", "fluid", "S0")
add("Potassium Chloride Infusion", ["kcl infusion","potassium chloride infusion"], ["20mmol/10ml","40mmol/20ml"], "IV", "electrolyte", "S4")
add("Sodium Chloride Hypertonic", ["hypertonic saline","nacl 3%"], ["3%"], "IV", "fluid", "S4")
add("Albumin", ["albumin","human albumin"], ["5%","20%"], "IV", "colloid", "S4")

# Build output
output = {
    "version": "2026.1",
    "country": "ZA",
    "source": "Based on South African Standard Treatment Guidelines and Essential Medicines List (STG/EML), National Department of Health",
    "drugs": drugs
}

outpath = "/Users/haohu/Documents/GitHub/emr/app/src/main/assets/formulary/za_formulary.json"
os.makedirs(os.path.dirname(outpath), exist_ok=True)
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Generated {len(drugs)} drugs to {outpath}")
