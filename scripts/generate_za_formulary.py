#!/usr/bin/env python3
"""Generate comprehensive South African drug formulary JSON.
Based on SA Standard Treatment Guidelines & Essential Medicines List (STG/EML).
"""
import json, os

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

# ══════════════════════════════════════════════════════════════
# ANTIBIOTICS (Penicillins)
# ══════════════════════════════════════════════════════════════
add("Amoxicillin", ["amoxil","amoxicillin","amoxycillin","amox","moxypen"], ["250mg","500mg","125mg/5ml"], "PO", "antibiotic", "S4")
add("Amoxicillin-Clavulanate", ["augmentin","co-amoxiclav","amoxiclav","amoxyclav"], ["375mg","625mg","1g","228mg/5ml"], "PO", "antibiotic", "S4")
add("Ampicillin", ["ampicillin","penbritin"], ["250mg","500mg","1g"], "PO", "antibiotic", "S4")
add("Ampicillin Injectable", ["ampicillin iv","ampicillin injection"], ["500mg","1g"], "IV", "antibiotic", "S4")
add("Flucloxacillin", ["flucloxacillin","floxapen","fluclox"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Phenoxymethylpenicillin", ["penicillin v","pen v","pen vk"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Benzylpenicillin", ["penicillin g","pen g","crystapen"], ["1MU","5MU"], "IV", "antibiotic", "S4")
add("Benzathine Penicillin", ["bicillin","penilente"], ["1.2MU","2.4MU"], "IM", "antibiotic", "S4")
add("Cloxacillin", ["cloxacillin","orbenin"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Piperacillin-Tazobactam", ["tazocin","piptaz","pip-taz"], ["4.5g"], "IV", "antibiotic", "S4")

# Cephalosporins
add("Cephalexin", ["cephalexin","cefalexin","keflex","cefasyn"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Cefuroxime", ["cefuroxime","zinacef","zinnat"], ["250mg","500mg","750mg","1.5g"], "PO", "antibiotic", "S4")
add("Ceftriaxone", ["ceftriaxone","rocephin","rocefin"], ["250mg","1g","2g"], "IV", "antibiotic", "S4")
add("Cefixime", ["cefixime","suprax"], ["200mg","400mg"], "PO", "antibiotic", "S4")
add("Cefazolin", ["cefazolin","kefzol"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefotaxime", ["cefotaxime","claforan"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Ceftazidime", ["ceftazidime","fortum"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefepime", ["cefepime","maxipime"], ["1g","2g"], "IV", "antibiotic", "S4")
add("Cefpodoxime", ["cefpodoxime","orelox"], ["100mg","200mg"], "PO", "antibiotic", "S4")

# Fluoroquinolones
add("Ciprofloxacin", ["ciprofloxacin","cipro","ciproxin"], ["250mg","500mg","750mg"], "PO", "antibiotic", "S4")
add("Ciprofloxacin Injectable", ["cipro iv","ciprofloxacin iv"], ["200mg/100ml","400mg/200ml"], "IV", "antibiotic", "S4")
add("Levofloxacin", ["levofloxacin","tavanic","levaquin"], ["250mg","500mg","750mg"], "PO", "antibiotic", "S4")
add("Moxifloxacin", ["moxifloxacin","avelox","moxiclav"], ["400mg"], "PO", "antibiotic", "S4")
add("Norfloxacin", ["norfloxacin","noroxin"], ["400mg"], "PO", "antibiotic", "S4")
add("Ofloxacin", ["ofloxacin","tarivid"], ["200mg","400mg"], "PO", "antibiotic", "S4")

# Macrolides
add("Azithromycin", ["azithromycin","zithromax","azithro","zmax"], ["250mg","500mg","200mg/5ml"], "PO", "antibiotic", "S4")
add("Erythromycin", ["erythromycin","eryc","erythrocin","erycinum"], ["250mg","500mg","125mg/5ml"], "PO", "antibiotic", "S4")
add("Clarithromycin", ["clarithromycin","klacid","biaxin"], ["250mg","500mg"], "PO", "antibiotic", "S4")

# Tetracyclines
add("Doxycycline", ["doxycycline","vibramycin","doxymycin","doxy"], ["100mg","200mg"], "PO", "antibiotic", "S4")
add("Tetracycline", ["tetracycline","achromycin"], ["250mg","500mg"], "PO", "antibiotic", "S4")
add("Minocycline", ["minocycline","minocin"], ["50mg","100mg"], "PO", "antibiotic", "S4")

# Aminoglycosides
add("Gentamicin", ["gentamicin","garamycin","genticin"], ["80mg/2ml","40mg/ml"], "IV", "antibiotic", "S4")
add("Amikacin", ["amikacin","amikin"], ["250mg/ml","500mg/2ml"], "IV", "antibiotic", "S4")
add("Tobramycin", ["tobramycin","nebcin"], ["80mg/2ml"], "IV", "antibiotic", "S4")

# Other antibiotics
add("Metronidazole", ["metronidazole","flagyl","metrogel","metro"], ["200mg","400mg","500mg/100ml"], "PO", "antibiotic", "S4")
add("Metronidazole Injectable", ["flagyl iv","metronidazole iv"], ["500mg/100ml"], "IV", "antibiotic", "S4")
add("Cotrimoxazole", ["cotrimoxazole","bactrim","septran","tmp-smx","co-trimoxazole"], ["480mg","960mg","240mg/5ml"], "PO", "antibiotic", "S4")
add("Clindamycin", ["clindamycin","dalacin","cleocin"], ["150mg","300mg","600mg"], "PO", "antibiotic", "S4")
add("Vancomycin", ["vancomycin","vancocin"], ["500mg","1g"], "IV", "antibiotic", "S4")
add("Linezolid", ["linezolid","zyvox","zyvoxid"], ["600mg"], "PO", "antibiotic", "S4")
add("Chloramphenicol", ["chloramphenicol","chloromycetin"], ["250mg","1g"], "PO", "antibiotic", "S4")
add("Nitrofurantoin", ["nitrofurantoin","macrodantin","macrobid"], ["50mg","100mg"], "PO", "antibiotic", "S4")
add("Fosfomycin", ["fosfomycin","monurol"], ["3g"], "PO", "antibiotic", "S4")
add("Colistin", ["colistin","colistimethate","colomycin"], ["1MU","2MU"], "IV", "antibiotic", "S4")
add("Meropenem", ["meropenem","meronem"], ["500mg","1g"], "IV", "antibiotic", "S4")
add("Imipenem-Cilastatin", ["imipenem","tienam"], ["500mg"], "IV", "antibiotic", "S4")
add("Ertapenem", ["ertapenem","invanz"], ["1g"], "IV", "antibiotic", "S4")
add("Trimethoprim", ["trimethoprim","monotrim"], ["100mg","200mg"], "PO", "antibiotic", "S4")
add("Nalidixic Acid", ["nalidixic acid","negram"], ["500mg"], "PO", "antibiotic", "S4")
add("Fusidic Acid Oral", ["fusidic acid","fucidin"], ["250mg"], "PO", "antibiotic", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIMALARIALS
# ══════════════════════════════════════════════════════════════
add("Artemether-Lumefantrine", ["coartem","artemether-lumefantrine","al","riamet"], ["20mg/120mg"], "PO", "antimalarial", "S4")
add("Quinine", ["quinine","qualaquin"], ["300mg","600mg/2ml"], "PO", "antimalarial", "S4")
add("Quinine Injectable", ["quinine iv","quinine injection"], ["600mg/2ml"], "IV", "antimalarial", "S4")
add("Chloroquine", ["chloroquine","plaquenil","nivaquine"], ["150mg","250mg"], "PO", "antimalarial", "S4")
add("Mefloquine", ["mefloquine","lariam"], ["250mg"], "PO", "antimalarial", "S4")
add("Atovaquone-Proguanil", ["malarone","atovaquone-proguanil"], ["250mg/100mg"], "PO", "antimalarial", "S4")
add("Primaquine", ["primaquine"], ["15mg","7.5mg"], "PO", "antimalarial", "S4")
add("Artesunate", ["artesunate"], ["60mg","120mg"], "IV", "antimalarial", "S4")
add("Sulfadoxine-Pyrimethamine", ["fansidar","sp"], ["500mg/25mg"], "PO", "antimalarial", "S4")
add("Proguanil", ["proguanil","paludrine"], ["100mg"], "PO", "antimalarial", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIRETROVIRALS (ARVs)
# ══════════════════════════════════════════════════════════════
add("Tenofovir Disoproxil", ["tenofovir","tdf","viread"], ["300mg"], "PO", "antiretroviral", "S4")
add("Lamivudine", ["lamivudine","3tc","epivir"], ["150mg","300mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("Emtricitabine", ["emtricitabine","ftc","emtriva"], ["200mg"], "PO", "antiretroviral", "S4")
add("Dolutegravir", ["dolutegravir","dtg","tivicay"], ["50mg"], "PO", "antiretroviral", "S4")
add("Efavirenz", ["efavirenz","efv","stocrin","sustiva"], ["600mg","200mg"], "PO", "antiretroviral", "S4")
add("TDF/3TC/DTG", ["tld","tenofovir-lamivudine-dolutegravir"], ["300mg/300mg/50mg"], "PO", "antiretroviral", "S4")
add("TDF/FTC/EFV", ["atripla","tef","tenofovir-emtricitabine-efavirenz"], ["300mg/200mg/600mg"], "PO", "antiretroviral", "S4")
add("TDF/3TC", ["tenofovir-lamivudine","tl"], ["300mg/300mg"], "PO", "antiretroviral", "S4")
add("TDF/FTC", ["truvada","tenofovir-emtricitabine"], ["300mg/200mg"], "PO", "antiretroviral", "S4")
add("Abacavir", ["abacavir","abc","ziagen"], ["300mg","600mg","20mg/ml"], "PO", "antiretroviral", "S4")
add("ABC/3TC", ["kivexa","abacavir-lamivudine"], ["600mg/300mg"], "PO", "antiretroviral", "S4")
add("Zidovudine", ["zidovudine","azt","retrovir"], ["100mg","300mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("AZT/3TC", ["combivir","zidovudine-lamivudine"], ["300mg/150mg"], "PO", "antiretroviral", "S4")
add("Nevirapine", ["nevirapine","nvp","viramune"], ["200mg","10mg/ml"], "PO", "antiretroviral", "S4")
add("Lopinavir-Ritonavir", ["lopinavir-ritonavir","lpv/r","aluvia","kaletra"], ["200mg/50mg","80mg/20mg/ml"], "PO", "antiretroviral", "S4")
add("Atazanavir", ["atazanavir","atv","reyataz"], ["300mg"], "PO", "antiretroviral", "S4")
add("Atazanavir-Ritonavir", ["atazanavir/ritonavir","atv/r"], ["300mg/100mg"], "PO", "antiretroviral", "S4")
add("Ritonavir", ["ritonavir","rtv","norvir"], ["100mg"], "PO", "antiretroviral", "S4")
add("Darunavir", ["darunavir","drv","prezista"], ["400mg","600mg"], "PO", "antiretroviral", "S4")
add("Raltegravir", ["raltegravir","ral","isentress"], ["400mg"], "PO", "antiretroviral", "S4")
add("Etravirine", ["etravirine","etv","intelence"], ["200mg"], "PO", "antiretroviral", "S4")
add("Tenofovir Alafenamide", ["tenofovir alafenamide","taf"], ["25mg"], "PO", "antiretroviral", "S4")

# ══════════════════════════════════════════════════════════════
# ANTI-TUBERCULOSIS
# ══════════════════════════════════════════════════════════════
add("Rifampicin", ["rifampicin","rifampin","rimactane","rifadin"], ["150mg","300mg","450mg","600mg"], "PO", "anti-TB", "S4")
add("Isoniazid", ["isoniazid","inh","rimifon"], ["100mg","300mg"], "PO", "anti-TB", "S4")
add("Pyrazinamide", ["pyrazinamide","pza","tebrazid"], ["500mg"], "PO", "anti-TB", "S4")
add("Ethambutol", ["ethambutol","emb","myambutol"], ["400mg"], "PO", "anti-TB", "S4")
add("RHZE Fixed-Dose", ["rhze","rifafour","4fdc"], ["150mg/75mg/400mg/275mg"], "PO", "anti-TB", "S4")
add("RH Fixed-Dose", ["rh","rifinah","2fdc"], ["150mg/75mg","300mg/150mg"], "PO", "anti-TB", "S4")
add("Streptomycin", ["streptomycin"], ["1g"], "IM", "anti-TB", "S4")
add("Bedaquiline", ["bedaquiline","sirturo"], ["100mg"], "PO", "anti-TB", "S4")
add("Delamanid", ["delamanid","deltyba"], ["50mg"], "PO", "anti-TB", "S4")
add("Pretomanid", ["pretomanid"], ["200mg"], "PO", "anti-TB", "S4")
add("Ethionamide", ["ethionamide","trecator"], ["250mg"], "PO", "anti-TB", "S4")
add("Cycloserine", ["cycloserine","seromycin"], ["250mg"], "PO", "anti-TB", "S4")
add("Para-aminosalicylic Acid", ["pas","paser","granupas"], ["4g"], "PO", "anti-TB", "S4")
add("Rifabutin", ["rifabutin","mycobutin"], ["150mg"], "PO", "anti-TB", "S4")

# ══════════════════════════════════════════════════════════════
# ANALGESICS & NSAIDs
# ══════════════════════════════════════════════════════════════
add("Paracetamol", ["paracetamol","panado","acetaminophen","tylenol","para"], ["500mg","1g","120mg/5ml"], "PO", "analgesic", "S0")
add("Paracetamol Suppository", ["panado suppository","paracetamol rectal"], ["125mg","250mg","500mg"], "PR", "analgesic", "S0")
add("Ibuprofen", ["ibuprofen","brufen","nurofen","ibupain"], ["200mg","400mg","600mg"], "PO", "NSAID", "S2")
add("Diclofenac", ["diclofenac","voltaren","cataflam","voltarol"], ["25mg","50mg","75mg","100mg"], "PO", "NSAID", "S3")
add("Diclofenac Injectable", ["voltaren injection","diclofenac im"], ["75mg/3ml"], "IM", "NSAID", "S3")
add("Diclofenac Topical", ["voltaren gel","voltaren emulgel","diclofenac gel"], ["1%","2%"], "TOP", "NSAID", "S2")
add("Naproxen", ["naproxen","naprosyn","aleve","synflex"], ["250mg","500mg"], "PO", "NSAID", "S3")
add("Indomethacin", ["indomethacin","indocid","indometacin"], ["25mg","50mg"], "PO", "NSAID", "S3")
add("Celecoxib", ["celecoxib","celebrex"], ["100mg","200mg"], "PO", "NSAID", "S3")
add("Meloxicam", ["meloxicam","mobic"], ["7.5mg","15mg"], "PO", "NSAID", "S3")
add("Aspirin", ["aspirin","disprin","ecotrin","acetylsalicylic acid","asa"], ["75mg","100mg","300mg","500mg"], "PO", "analgesic", "S2")
add("Piroxicam", ["piroxicam","feldene"], ["10mg","20mg"], "PO", "NSAID", "S3")
add("Mefenamic Acid", ["mefenamic acid","ponstan","ponstyl"], ["250mg","500mg"], "PO", "NSAID", "S3")

# Opioids
add("Tramadol", ["tramadol","tramal","ultram"], ["50mg","100mg"], "PO", "opioid analgesic", "S5")
add("Tramadol Injectable", ["tramadol injection","tramal injection"], ["100mg/2ml"], "IV", "opioid analgesic", "S5")
add("Morphine Oral", ["morphine","mst","oramorph"], ["10mg","15mg","30mg","60mg"], "PO", "opioid analgesic", "S7")
add("Morphine Injectable", ["morphine injection","morphine sulfate"], ["10mg/ml","15mg/ml"], "IV", "opioid analgesic", "S7")
add("Codeine", ["codeine","codeine phosphate"], ["15mg","30mg","60mg"], "PO", "opioid analgesic", "S5")
add("Paracetamol-Codeine", ["paracod","co-codamol","panado-codeine","stopayne"], ["500mg/8mg","500mg/30mg"], "PO", "opioid analgesic", "S5")
add("Pethidine", ["pethidine","meperidine","demerol"], ["50mg","100mg/2ml"], "IM", "opioid analgesic", "S7")
add("Fentanyl Patch", ["fentanyl","durogesic","fentanyl patch"], ["12mcg/hr","25mcg/hr","50mcg/hr","75mcg/hr","100mcg/hr"], "TD", "opioid analgesic", "S7")
add("Fentanyl Injectable", ["fentanyl injection","sublimaze"], ["50mcg/ml","100mcg/2ml"], "IV", "opioid analgesic", "S7")
add("Oxycodone", ["oxycodone","oxycontin","oxynorm"], ["5mg","10mg","20mg"], "PO", "opioid analgesic", "S7")
add("Dihydrocodeine", ["dihydrocodeine","dhc continus"], ["30mg","60mg"], "PO", "opioid analgesic", "S5")
add("Tilidine", ["tilidine","valoron"], ["50mg"], "PO", "opioid analgesic", "S5")
add("Naloxone", ["naloxone","narcan"], ["0.4mg/ml","1mg/ml"], "IV", "opioid antagonist", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIHYPERTENSIVES
# ══════════════════════════════════════════════════════════════
# CCBs
add("Amlodipine", ["amlodipine","norvasc","amloc","asomex"], ["5mg","10mg"], "PO", "antihypertensive", "S3")
add("Nifedipine", ["nifedipine","adalat","procardia"], ["10mg","20mg","30mg","60mg"], "PO", "antihypertensive", "S3")
add("Felodipine", ["felodipine","plendil"], ["5mg","10mg"], "PO", "antihypertensive", "S3")
# ACEi
add("Enalapril", ["enalapril","renitec","enap","vasotec"], ["5mg","10mg","20mg"], "PO", "antihypertensive", "S3")
add("Perindopril", ["perindopril","coversyl","prexum"], ["4mg","8mg"], "PO", "antihypertensive", "S3")
add("Ramipril", ["ramipril","tritace","altace"], ["2.5mg","5mg","10mg"], "PO", "antihypertensive", "S3")
add("Lisinopril", ["lisinopril","zestril","prinivil"], ["5mg","10mg","20mg"], "PO", "antihypertensive", "S3")
add("Captopril", ["captopril","capoten"], ["12.5mg","25mg","50mg"], "PO", "antihypertensive", "S3")
# ARBs
add("Losartan", ["losartan","cozaar","lozar"], ["50mg","100mg"], "PO", "antihypertensive", "S3")
add("Valsartan", ["valsartan","diovan","tareg"], ["80mg","160mg","320mg"], "PO", "antihypertensive", "S3")
add("Irbesartan", ["irbesartan","aprovel","avapro"], ["150mg","300mg"], "PO", "antihypertensive", "S3")
add("Telmisartan", ["telmisartan","micardis","pritor"], ["40mg","80mg"], "PO", "antihypertensive", "S3")
add("Candesartan", ["candesartan","atacand","blopress"], ["8mg","16mg","32mg"], "PO", "antihypertensive", "S3")
# Diuretics
add("Hydrochlorothiazide", ["hydrochlorothiazide","hctz","ridaq","esidrix"], ["12.5mg","25mg"], "PO", "diuretic", "S3")
add("Indapamide", ["indapamide","natrilix","lozide"], ["1.5mg","2.5mg"], "PO", "diuretic", "S3")
add("Furosemide", ["furosemide","lasix","frusemide","lasikal"], ["40mg","80mg","20mg/2ml"], "PO", "diuretic", "S3")
add("Furosemide Injectable", ["lasix iv","furosemide injection"], ["20mg/2ml"], "IV", "diuretic", "S3")
add("Spironolactone", ["spironolactone","aldactone"], ["25mg","50mg","100mg"], "PO", "diuretic", "S3")
add("Chlorthalidone", ["chlorthalidone","hygroton"], ["12.5mg","25mg"], "PO", "diuretic", "S3")
add("Amiloride", ["amiloride","midamor"], ["5mg"], "PO", "diuretic", "S3")
add("Mannitol", ["mannitol"], ["20%"], "IV", "diuretic", "S4")
# Beta-blockers
add("Atenolol", ["atenolol","tenormin","atenol"], ["50mg","100mg"], "PO", "beta-blocker", "S3")
add("Bisoprolol", ["bisoprolol","concor","cardicor"], ["2.5mg","5mg","10mg"], "PO", "beta-blocker", "S3")
add("Carvedilol", ["carvedilol","coreg","dilatrend"], ["6.25mg","12.5mg","25mg"], "PO", "beta-blocker", "S3")
add("Metoprolol", ["metoprolol","lopressor","betaloc"], ["50mg","100mg","200mg"], "PO", "beta-blocker", "S3")
add("Propranolol", ["propranolol","inderal"], ["10mg","40mg","80mg"], "PO", "beta-blocker", "S3")
# Alpha-blockers & others
add("Prazosin", ["prazosin","minipress"], ["1mg","2mg","5mg"], "PO", "antihypertensive", "S3")
add("Doxazosin", ["doxazosin","cardura"], ["1mg","2mg","4mg"], "PO", "antihypertensive", "S3")
add("Methyldopa", ["methyldopa","aldomet"], ["250mg","500mg"], "PO", "antihypertensive", "S4")
add("Hydralazine", ["hydralazine","apresoline"], ["25mg","50mg","20mg/ml"], "PO", "antihypertensive", "S4")
add("Hydralazine Injectable", ["hydralazine injection","apresoline iv"], ["20mg/ml"], "IV", "antihypertensive", "S4")
add("Clonidine", ["clonidine","catapres","dixarit"], ["0.1mg","0.15mg","0.2mg"], "PO", "antihypertensive", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIDIABETICS
# ══════════════════════════════════════════════════════════════
add("Metformin", ["metformin","glucophage","metfin","glycomet"], ["500mg","850mg","1000mg"], "PO", "antidiabetic", "S3")
add("Glibenclamide", ["glibenclamide","daonil","glyburide","euglucon"], ["2.5mg","5mg"], "PO", "antidiabetic", "S3")
add("Gliclazide", ["gliclazide","diamicron","diamicron mr"], ["40mg","80mg","30mg","60mg"], "PO", "antidiabetic", "S3")
add("Glimepiride", ["glimepiride","amaryl"], ["1mg","2mg","3mg","4mg"], "PO", "antidiabetic", "S3")
add("Pioglitazone", ["pioglitazone","actos"], ["15mg","30mg","45mg"], "PO", "antidiabetic", "S3")
add("Sitagliptin", ["sitagliptin","januvia"], ["25mg","50mg","100mg"], "PO", "antidiabetic", "S3")
add("Vildagliptin", ["vildagliptin","galvus"], ["50mg"], "PO", "antidiabetic", "S3")
add("Empagliflozin", ["empagliflozin","jardiance"], ["10mg","25mg"], "PO", "antidiabetic", "S3")
add("Dapagliflozin", ["dapagliflozin","forxiga"], ["5mg","10mg"], "PO", "antidiabetic", "S3")
add("Metformin-Sitagliptin", ["janumet","sitagliptin-metformin"], ["50mg/500mg","50mg/1000mg"], "PO", "antidiabetic", "S3")
add("Insulin Regular", ["actrapid","humulin r","regular insulin","soluble insulin"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin NPH", ["protaphane","humulin n","isophane insulin","nph insulin"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Glargine", ["lantus","basaglar","toujeo","insulin glargine"], ["100IU/ml","300IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Aspart", ["novorapid","fiasp","insulin aspart"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Lispro", ["humalog","insulin lispro"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Premixed 30/70", ["novomix 30","humulin 30/70","mixtard"], ["100IU/ml"], "SC", "antidiabetic", "S4")
add("Insulin Degludec", ["tresiba","insulin degludec"], ["100IU/ml","200IU/ml"], "SC", "antidiabetic", "S4")
add("Liraglutide", ["victoza","saxenda","liraglutide"], ["6mg/ml"], "SC", "antidiabetic", "S4")
add("Semaglutide Injectable", ["ozempic","semaglutide"], ["0.25mg","0.5mg","1mg"], "SC", "antidiabetic", "S4")
add("Glucose", ["glucose","dextrose","glucose 50%"], ["50%"], "IV", "antidiabetic", "S0")

# ══════════════════════════════════════════════════════════════
# CARDIOVASCULAR / LIPID / ANTICOAGULANTS
# ══════════════════════════════════════════════════════════════
add("Simvastatin", ["simvastatin","zocor","simvacor"], ["10mg","20mg","40mg"], "PO", "statin", "S3")
add("Atorvastatin", ["atorvastatin","lipitor","aspavor"], ["10mg","20mg","40mg","80mg"], "PO", "statin", "S3")
add("Rosuvastatin", ["rosuvastatin","crestor"], ["5mg","10mg","20mg","40mg"], "PO", "statin", "S3")
add("Pravastatin", ["pravastatin","pravachol"], ["20mg","40mg"], "PO", "statin", "S3")
add("Ezetimibe", ["ezetimibe","ezetrol","zetia"], ["10mg"], "PO", "lipid-lowering", "S3")
add("Fenofibrate", ["fenofibrate","lipanthyl","tricor"], ["145mg","160mg","200mg"], "PO", "lipid-lowering", "S3")
add("Gemfibrozil", ["gemfibrozil","lopid"], ["300mg","600mg"], "PO", "lipid-lowering", "S3")
add("Warfarin", ["warfarin","coumadin","marevan"], ["1mg","2mg","3mg","5mg"], "PO", "anticoagulant", "S4")
add("Enoxaparin", ["enoxaparin","clexane","lovenox"], ["20mg","40mg","60mg","80mg","100mg"], "SC", "anticoagulant", "S4")
add("Heparin", ["heparin","hep-lock","heparin sodium"], ["5000IU/ml","25000IU/5ml"], "IV", "anticoagulant", "S4")
add("Rivaroxaban", ["rivaroxaban","xarelto"], ["10mg","15mg","20mg"], "PO", "anticoagulant", "S4")
add("Apixaban", ["apixaban","eliquis"], ["2.5mg","5mg"], "PO", "anticoagulant", "S4")
add("Clopidogrel", ["clopidogrel","plavix","clopilet"], ["75mg"], "PO", "antiplatelet", "S3")
add("Dipyridamole", ["dipyridamole","persantin"], ["75mg","200mg"], "PO", "antiplatelet", "S3")
add("Ticagrelor", ["ticagrelor","brilinta"], ["60mg","90mg"], "PO", "antiplatelet", "S4")
add("Digoxin", ["digoxin","lanoxin"], ["0.0625mg","0.125mg","0.25mg"], "PO", "cardiac glycoside", "S4")
add("Amiodarone", ["amiodarone","cordarone","pacerone"], ["100mg","200mg","150mg/3ml"], "PO", "antiarrhythmic", "S4")
add("Amiodarone Injectable", ["amiodarone iv","cordarone iv"], ["150mg/3ml"], "IV", "antiarrhythmic", "S4")
add("Diltiazem", ["diltiazem","cardizem","tildiem"], ["60mg","90mg","120mg","180mg","240mg"], "PO", "calcium channel blocker", "S3")
add("Verapamil", ["verapamil","isoptin","calan"], ["40mg","80mg","120mg","240mg"], "PO", "calcium channel blocker", "S3")
add("Isosorbide Dinitrate", ["isosorbide dinitrate","isordil","isdn"], ["5mg","10mg","20mg","40mg"], "PO", "nitrate", "S3")
add("Isosorbide Mononitrate", ["isosorbide mononitrate","imdur","ismn"], ["20mg","60mg"], "PO", "nitrate", "S3")
add("Glyceryl Trinitrate", ["gtn","nitroglycerin","nitrolingual","nitrostat"], ["0.5mg","5mg/ml"], "SL", "nitrate", "S3")
add("GTN Patch", ["nitro-dur","gtn patch","nitroglycerin patch"], ["5mg/24hr","10mg/24hr"], "TD", "nitrate", "S3")
add("Streptokinase", ["streptokinase","streptase"], ["1.5MU"], "IV", "thrombolytic", "S4")
add("Dobutamine", ["dobutamine","dobutrex"], ["250mg/20ml"], "IV", "inotrope", "S4")
add("Dopamine", ["dopamine","intropin"], ["200mg/5ml"], "IV", "inotrope", "S4")

# ══════════════════════════════════════════════════════════════
# RESPIRATORY
# ══════════════════════════════════════════════════════════════
add("Salbutamol Inhaler", ["salbutamol","ventolin","asthavent","albuterol"], ["100mcg/puff"], "INH", "bronchodilator", "S3")
add("Salbutamol Nebuliser", ["salbutamol neb","ventolin neb"], ["5mg/ml","2.5mg/2.5ml"], "INH", "bronchodilator", "S3")
add("Salbutamol Oral", ["salbutamol oral","ventolin syrup"], ["2mg","4mg","2mg/5ml"], "PO", "bronchodilator", "S3")
add("Ipratropium Bromide", ["ipratropium","atrovent"], ["20mcg/puff","250mcg/ml"], "INH", "bronchodilator", "S3")
add("Salbutamol-Ipratropium", ["combivent","duolin","duovent"], ["100mcg/20mcg","2.5mg/0.5mg"], "INH", "bronchodilator", "S3")
add("Beclomethasone", ["beclomethasone","becotide","becloforte","qvar"], ["50mcg","100mcg","200mcg","250mcg"], "INH", "corticosteroid", "S4")
add("Budesonide Inhaler", ["budesonide","pulmicort"], ["100mcg","200mcg","400mcg"], "INH", "corticosteroid", "S4")
add("Budesonide Nebuliser", ["pulmicort neb","budesonide neb"], ["0.5mg/2ml","1mg/2ml"], "INH", "corticosteroid", "S4")
add("Fluticasone", ["fluticasone","flixotide","flovent"], ["50mcg","125mcg","250mcg"], "INH", "corticosteroid", "S4")
add("Salmeterol", ["salmeterol","serevent"], ["25mcg"], "INH", "LABA", "S3")
add("Formoterol", ["formoterol","foradil","oxis"], ["12mcg"], "INH", "LABA", "S3")
add("Budesonide-Formoterol", ["symbicort","budesonide-formoterol"], ["80/4.5mcg","160/4.5mcg","320/9mcg"], "INH", "ICS-LABA", "S4")
add("Fluticasone-Salmeterol", ["seretide","advair","fluticasone-salmeterol"], ["100/50mcg","250/50mcg","500/50mcg"], "INH", "ICS-LABA", "S4")
add("Montelukast", ["montelukast","singulair"], ["4mg","5mg","10mg"], "PO", "leukotriene antagonist", "S3")
add("Theophylline", ["theophylline","nuelin","theo-dur","theolair"], ["100mg","200mg","300mg"], "PO", "bronchodilator", "S3")
add("Aminophylline", ["aminophylline","phyllocontin"], ["100mg","225mg","250mg/10ml"], "PO", "bronchodilator", "S4")
add("Aminophylline Injectable", ["aminophylline iv"], ["250mg/10ml"], "IV", "bronchodilator", "S4")
add("Tiotropium", ["tiotropium","spiriva"], ["18mcg","2.5mcg"], "INH", "LAMA", "S3")

# ══════════════════════════════════════════════════════════════
# GASTROINTESTINAL
# ══════════════════════════════════════════════════════════════
add("Omeprazole", ["omeprazole","losec","altosec","prilosec"], ["10mg","20mg","40mg"], "PO", "PPI", "S3")
add("Lansoprazole", ["lansoprazole","lanzor","zoton","prevacid"], ["15mg","30mg"], "PO", "PPI", "S3")
add("Pantoprazole", ["pantoprazole","controloc","protonix"], ["20mg","40mg"], "PO", "PPI", "S3")
add("Esomeprazole", ["esomeprazole","nexium","nexiam"], ["20mg","40mg"], "PO", "PPI", "S3")
add("Ranitidine", ["ranitidine","zantac"], ["150mg","300mg"], "PO", "H2 blocker", "S2")
add("Cimetidine", ["cimetidine","tagamet"], ["200mg","400mg","800mg"], "PO", "H2 blocker", "S2")
add("Metoclopramide", ["metoclopramide","maxolon","reglan"], ["10mg","10mg/2ml"], "PO", "antiemetic", "S4")
add("Domperidone", ["domperidone","motilium"], ["10mg"], "PO", "antiemetic", "S3")
add("Ondansetron", ["ondansetron","zofran"], ["4mg","8mg","4mg/2ml"], "PO", "antiemetic", "S4")
add("Ondansetron Injectable", ["ondansetron iv","zofran iv"], ["4mg/2ml","8mg/4ml"], "IV", "antiemetic", "S4")
add("Promethazine", ["promethazine","phenergan","promethegan"], ["10mg","25mg"], "PO", "antiemetic", "S3")
add("Loperamide", ["loperamide","imodium"], ["2mg"], "PO", "antidiarrheal", "S2")
add("Hyoscine Butylbromide", ["hyoscine","buscopan","scopolamine"], ["10mg","20mg/ml"], "PO", "antispasmodic", "S2")
add("ORS", ["ors","oral rehydration salts","rehydration salts","ors sachet"], ["sachet"], "PO", "rehydration", "S0")
add("Activated Charcoal", ["activated charcoal","carbomix","charcodote"], ["50g"], "PO", "antidote", "S0")
add("Lactulose", ["lactulose","duphalac","laevolac"], ["10g/15ml"], "PO", "laxative", "S1")
add("Bisacodyl", ["bisacodyl","dulcolax"], ["5mg","10mg"], "PO", "laxative", "S1")
add("Senna", ["senna","senokot"], ["7.5mg","15mg"], "PO", "laxative", "S0")
add("Docusate", ["docusate","colace","coloxyl"], ["100mg"], "PO", "laxative", "S1")
add("Mesalazine", ["mesalazine","asacol","pentasa","salofalk"], ["250mg","500mg","1g"], "PO", "anti-inflammatory GI", "S4")
add("Sulfasalazine", ["sulfasalazine","salazopyrin"], ["500mg"], "PO", "anti-inflammatory GI", "S4")
add("Sucralfate", ["sucralfate","ulcyte","carafate"], ["1g"], "PO", "GI protectant", "S3")
add("Aluminium Hydroxide", ["antacid","maalox","mylanta","aluminium hydroxide"], ["500mg"], "PO", "antacid", "S0")
add("Magnesium Trisilicate", ["magnesium trisilicate","gastropax"], ["500mg"], "PO", "antacid", "S0")

# ══════════════════════════════════════════════════════════════
# ANTIFUNGALS
# ══════════════════════════════════════════════════════════════
add("Fluconazole", ["fluconazole","diflucan","flucazole"], ["50mg","150mg","200mg","2mg/ml"], "PO", "antifungal", "S4")
add("Itraconazole", ["itraconazole","sporanox"], ["100mg"], "PO", "antifungal", "S4")
add("Ketoconazole", ["ketoconazole","nizoral"], ["200mg"], "PO", "antifungal", "S4")
add("Nystatin", ["nystatin","mycostatin","nilstat"], ["100000IU/ml"], "PO", "antifungal", "S2")
add("Clotrimazole", ["clotrimazole","canesten","lotriderm"], ["1%","500mg"], "TOP", "antifungal", "S2")
add("Clotrimazole Vaginal", ["clotrimazole pessary","canesten vaginal"], ["100mg","500mg"], "VAG", "antifungal", "S2")
add("Miconazole", ["miconazole","daktarin"], ["2%"], "TOP", "antifungal", "S2")
add("Terbinafine", ["terbinafine","lamisil"], ["250mg","1%"], "PO", "antifungal", "S3")
add("Amphotericin B", ["amphotericin b","fungizone","amphocil"], ["50mg"], "IV", "antifungal", "S4")
add("Griseofulvin", ["griseofulvin","grisovin","fulcin"], ["125mg","250mg","500mg"], "PO", "antifungal", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIVIRALS (non-ARV)
# ══════════════════════════════════════════════════════════════
add("Acyclovir", ["acyclovir","aciclovir","zovirax"], ["200mg","400mg","800mg"], "PO", "antiviral", "S4")
add("Acyclovir Injectable", ["acyclovir iv","zovirax iv"], ["250mg","500mg"], "IV", "antiviral", "S4")
add("Valacyclovir", ["valacyclovir","valaciclovir","valtrex"], ["500mg","1g"], "PO", "antiviral", "S4")
add("Oseltamivir", ["oseltamivir","tamiflu"], ["75mg"], "PO", "antiviral", "S4")
add("Ganciclovir", ["ganciclovir","cymevene","cytovene"], ["250mg","500mg"], "IV", "antiviral", "S4")
add("Valganciclovir", ["valganciclovir","valcyte"], ["450mg"], "PO", "antiviral", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIPARASITICS
# ══════════════════════════════════════════════════════════════
add("Mebendazole", ["mebendazole","vermox"], ["100mg","500mg"], "PO", "anthelmintic", "S2")
add("Albendazole", ["albendazole","zentel","eskazole"], ["200mg","400mg"], "PO", "anthelmintic", "S2")
add("Praziquantel", ["praziquantel","biltricide","distocide"], ["600mg"], "PO", "anthelmintic", "S4")
add("Ivermectin", ["ivermectin","stromectol","mectizan"], ["3mg","6mg"], "PO", "antiparasitic", "S4")
add("Pyrantel", ["pyrantel","combantrin"], ["125mg","250mg"], "PO", "anthelmintic", "S2")
add("Niclosamide", ["niclosamide","yomesan"], ["500mg"], "PO", "anthelmintic", "S4")
add("Metrifonate", ["metrifonate","bilarcil"], ["100mg"], "PO", "anthelmintic", "S4")
add("Permethrin", ["permethrin","nix","lyclear"], ["5%","1%"], "TOP", "antiparasitic", "S2")
add("Benzyl Benzoate", ["benzyl benzoate","ascabiol"], ["25%"], "TOP", "antiparasitic", "S2")

# ══════════════════════════════════════════════════════════════
# PSYCHIATRIC / NEUROLOGICAL
# ══════════════════════════════════════════════════════════════
add("Amitriptyline", ["amitriptyline","elavil","trepiline"], ["10mg","25mg","50mg","75mg"], "PO", "antidepressant", "S4")
add("Fluoxetine", ["fluoxetine","prozac","lilly","nuzak"], ["20mg","40mg"], "PO", "antidepressant", "S4")
add("Sertraline", ["sertraline","zoloft","serdep"], ["50mg","100mg"], "PO", "antidepressant", "S4")
add("Citalopram", ["citalopram","cipramil","celexa"], ["10mg","20mg","40mg"], "PO", "antidepressant", "S4")
add("Escitalopram", ["escitalopram","cipralex","lexapro"], ["5mg","10mg","20mg"], "PO", "antidepressant", "S4")
add("Venlafaxine", ["venlafaxine","efexor","effexor"], ["37.5mg","75mg","150mg"], "PO", "antidepressant", "S4")
add("Mirtazapine", ["mirtazapine","remeron"], ["15mg","30mg","45mg"], "PO", "antidepressant", "S4")
add("Imipramine", ["imipramine","tofranil"], ["10mg","25mg"], "PO", "antidepressant", "S4")
add("Haloperidol", ["haloperidol","haldol","serenace"], ["0.5mg","1.5mg","5mg","5mg/ml"], "PO", "antipsychotic", "S5")
add("Haloperidol Injectable", ["haldol injection","haloperidol im"], ["5mg/ml"], "IM", "antipsychotic", "S5")
add("Chlorpromazine", ["chlorpromazine","largactil","thorazine"], ["25mg","50mg","100mg"], "PO", "antipsychotic", "S5")
add("Risperidone", ["risperidone","risperdal"], ["0.5mg","1mg","2mg","3mg","4mg"], "PO", "antipsychotic", "S5")
add("Olanzapine", ["olanzapine","zyprexa"], ["2.5mg","5mg","10mg"], "PO", "antipsychotic", "S5")
add("Quetiapine", ["quetiapine","seroquel"], ["25mg","100mg","200mg","300mg"], "PO", "antipsychotic", "S5")
add("Lithium Carbonate", ["lithium","camcolit","priadel"], ["250mg","400mg"], "PO", "mood stabilizer", "S5")
add("Sodium Valproate", ["sodium valproate","epilim","valproic acid","depakote"], ["200mg","500mg","200mg/5ml"], "PO", "anticonvulsant", "S4")
add("Carbamazepine", ["carbamazepine","tegretol","epitol"], ["100mg","200mg","400mg","100mg/5ml"], "PO", "anticonvulsant", "S4")
add("Phenytoin", ["phenytoin","dilantin","epanutin"], ["100mg","50mg/5ml","250mg/5ml"], "PO", "anticonvulsant", "S4")
add("Phenytoin Injectable", ["phenytoin iv","dilantin iv"], ["250mg/5ml"], "IV", "anticonvulsant", "S4")
add("Lamotrigine", ["lamotrigine","lamictal"], ["25mg","50mg","100mg","200mg"], "PO", "anticonvulsant", "S4")
add("Levetiracetam", ["levetiracetam","keppra"], ["250mg","500mg","750mg","1000mg"], "PO", "anticonvulsant", "S4")
add("Topiramate", ["topiramate","topamax"], ["25mg","50mg","100mg","200mg"], "PO", "anticonvulsant", "S4")
add("Phenobarbital", ["phenobarbital","phenobarbitone","luminal"], ["30mg","60mg","100mg"], "PO", "anticonvulsant", "S5")
add("Phenobarbital Injectable", ["phenobarbital injection"], ["200mg/ml"], "IM", "anticonvulsant", "S5")
add("Diazepam", ["diazepam","valium"], ["2mg","5mg","10mg","5mg/ml"], "PO", "benzodiazepine", "S5")
add("Diazepam Injectable", ["diazepam iv","valium injection"], ["10mg/2ml"], "IV", "benzodiazepine", "S5")
add("Diazepam Rectal", ["diazepam rectal","stesolid"], ["5mg","10mg"], "PR", "benzodiazepine", "S5")
add("Lorazepam", ["lorazepam","ativan"], ["0.5mg","1mg","2mg","4mg/ml"], "PO", "benzodiazepine", "S5")
add("Midazolam", ["midazolam","dormicum","versed"], ["7.5mg","15mg","5mg/ml"], "PO", "benzodiazepine", "S5")
add("Midazolam Injectable", ["midazolam iv","dormicum injection"], ["5mg/ml","15mg/3ml"], "IV", "benzodiazepine", "S5")
add("Clonazepam", ["clonazepam","rivotril"], ["0.5mg","2mg"], "PO", "benzodiazepine", "S5")
add("Zolpidem", ["zolpidem","stilnox","ambien"], ["5mg","10mg"], "PO", "sedative", "S5")
add("Hydroxyzine", ["hydroxyzine","atarax","vistaril"], ["10mg","25mg"], "PO", "anxiolytic", "S3")

# ══════════════════════════════════════════════════════════════
# ENDOCRINE / HORMONES
# ══════════════════════════════════════════════════════════════
add("Levothyroxine", ["levothyroxine","eltroxin","euthyrox","synthroid"], ["25mcg","50mcg","100mcg","150mcg","200mcg"], "PO", "thyroid", "S4")
add("Carbimazole", ["carbimazole","neo-mercazole"], ["5mg","10mg","20mg"], "PO", "anti-thyroid", "S4")
add("Propylthiouracil", ["propylthiouracil","ptu"], ["50mg"], "PO", "anti-thyroid", "S4")
add("Prednisolone", ["prednisolone","pediapred","prelone"], ["5mg","20mg","40mg","15mg/5ml"], "PO", "corticosteroid", "S4")
add("Prednisone", ["prednisone","deltasone","meticorten"], ["5mg","10mg","20mg","50mg"], "PO", "corticosteroid", "S4")
add("Dexamethasone", ["dexamethasone","decadron"], ["0.5mg","4mg","4mg/ml"], "PO", "corticosteroid", "S4")
add("Dexamethasone Injectable", ["dexamethasone iv","decadron injection"], ["4mg/ml","8mg/2ml"], "IV", "corticosteroid", "S4")
add("Hydrocortisone Oral", ["hydrocortisone","cortef"], ["10mg","20mg"], "PO", "corticosteroid", "S4")
add("Hydrocortisone Injectable", ["solu-cortef","hydrocortisone iv"], ["100mg","250mg","500mg"], "IV", "corticosteroid", "S4")
add("Methylprednisolone", ["methylprednisolone","solu-medrol","medrol"], ["4mg","16mg","500mg","1g"], "PO", "corticosteroid", "S4")
add("Fludrocortisone", ["fludrocortisone","florinef"], ["0.1mg"], "PO", "corticosteroid", "S4")
add("Betamethasone Injectable", ["betamethasone","celestone"], ["4mg/ml"], "IM", "corticosteroid", "S4")
add("Triamcinolone Injectable", ["triamcinolone","kenalog"], ["40mg/ml"], "IM", "corticosteroid", "S4")

# Contraceptives / Reproductive
add("Combined Oral Contraceptive", ["combined pill","ocp","nordette","triphasil","yasmin"], ["EE/LNG","EE/DSG"], "PO", "contraceptive", "S3")
add("Progesterone-Only Pill", ["mini pill","pop","noriday","microval","nur-isterate"], ["norethisterone 0.35mg"], "PO", "contraceptive", "S3")
add("Medroxyprogesterone Depot", ["depo-provera","depo","petogen","medroxyprogesterone"], ["150mg/ml"], "IM", "contraceptive", "S4")
add("Etonogestrel Implant", ["implanon","nexplanon","implanon nxt"], ["68mg"], "SC", "contraceptive", "S4")
add("Levonorgestrel Emergency", ["plan b","norlevo","escapelle","emergency contraceptive"], ["1.5mg","0.75mg"], "PO", "contraceptive", "S3")
add("Copper IUD", ["copper iud","copper t","paragard","nova-t"], ["device"], "IU", "contraceptive", "S4")
add("Norethisterone", ["norethisterone","primolut n","noristerat"], ["5mg","200mg/ml"], "PO", "hormone", "S4")
add("Conjugated Estrogens", ["premarin","conjugated estrogens"], ["0.3mg","0.625mg","1.25mg"], "PO", "hormone", "S4")
add("Estradiol Valerate", ["estradiol","progynova"], ["1mg","2mg"], "PO", "hormone", "S4")
add("Testosterone", ["testosterone","sustanon","depo-testosterone","nebido"], ["250mg/ml"], "IM", "hormone", "S5")
add("Tamoxifen", ["tamoxifen","nolvadex"], ["10mg","20mg"], "PO", "antineoplastic", "S4")
add("Letrozole", ["letrozole","femara"], ["2.5mg"], "PO", "antineoplastic", "S4")

# ══════════════════════════════════════════════════════════════
# SUPPLEMENTS / VITAMINS
# ══════════════════════════════════════════════════════════════
add("Ferrous Sulfate", ["ferrous sulfate","iron","feso4","ferrous sulphate","fefol"], ["200mg","325mg"], "PO", "supplement", "S0")
add("Folic Acid", ["folic acid","folate","fa"], ["5mg","1mg"], "PO", "supplement", "S0")
add("Ferrous Sulfate-Folic Acid", ["fefol","ferro-folic","iron-folic acid"], ["200mg/0.5mg"], "PO", "supplement", "S0")
add("Vitamin B Complex", ["vitamin b complex","b complex","neurobion"], ["tablet"], "PO", "supplement", "S0")
add("Vitamin B12", ["vitamin b12","cyanocobalamin","hydroxocobalamin"], ["1mg","1mg/ml"], "PO", "supplement", "S0")
add("Vitamin B12 Injectable", ["b12 injection","cyanocobalamin injection","hydroxocobalamin injection"], ["1mg/ml"], "IM", "supplement", "S2")
add("Vitamin D3", ["vitamin d","cholecalciferol","calciferol"], ["400IU","1000IU","50000IU"], "PO", "supplement", "S0")
add("Calcium Carbonate", ["calcium","caltrate","oscal","calcium carbonate"], ["500mg","1250mg"], "PO", "supplement", "S0")
add("Calcium Gluconate Injectable", ["calcium gluconate","calcium iv"], ["10%","10ml"], "IV", "supplement", "S4")
add("Magnesium Sulfate Injectable", ["magnesium sulfate","mgso4","epsom salt"], ["50%","2g/4ml","5g/10ml"], "IV", "supplement", "S4")
add("Potassium Chloride", ["potassium chloride","slow-k","kcl"], ["600mg","8mmol"], "PO", "supplement", "S2")
add("Zinc", ["zinc","zinc sulfate"], ["20mg"], "PO", "supplement", "S0")
add("Multivitamin", ["multivitamin","centrum","mvt"], ["tablet"], "PO", "supplement", "S0")
add("Pyridoxine", ["pyridoxine","vitamin b6"], ["25mg","50mg"], "PO", "supplement", "S0")
add("Thiamine", ["thiamine","vitamin b1"], ["100mg","300mg"], "PO", "supplement", "S0")
add("Thiamine Injectable", ["thiamine injection","vitamin b1 injection"], ["100mg/ml"], "IM", "supplement", "S2")
add("Ascorbic Acid", ["vitamin c","ascorbic acid"], ["100mg","250mg","500mg","1g"], "PO", "supplement", "S0")
add("Retinol", ["vitamin a","retinol"], ["50000IU","200000IU"], "PO", "supplement", "S0")

# ══════════════════════════════════════════════════════════════
# OPHTHALMIC
# ══════════════════════════════════════════════════════════════
add("Chloramphenicol Eye Drops", ["chloramphenicol eye drops","chloromycetin eye"], ["0.5%"], "OPH", "ophthalmic antibiotic", "S4")
add("Chloramphenicol Eye Ointment", ["chloramphenicol eye ointment"], ["1%"], "OPH", "ophthalmic antibiotic", "S4")
add("Ciprofloxacin Eye Drops", ["ciprofloxacin eye drops","ciloxan"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Tobramycin Eye Drops", ["tobramycin eye drops","tobrex"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Gentamicin Eye Drops", ["gentamicin eye drops","garamycin eye"], ["0.3%"], "OPH", "ophthalmic antibiotic", "S4")
add("Tetracycline Eye Ointment", ["tetracycline eye ointment","achromycin eye"], ["1%"], "OPH", "ophthalmic antibiotic", "S4")
add("Timolol Eye Drops", ["timolol eye drops","timoptol","timolol"], ["0.25%","0.5%"], "OPH", "antiglaucoma", "S3")
add("Pilocarpine Eye Drops", ["pilocarpine","isopto carpine"], ["2%","4%"], "OPH", "antiglaucoma", "S3")
add("Latanoprost Eye Drops", ["latanoprost","xalatan"], ["0.005%"], "OPH", "antiglaucoma", "S3")
add("Atropine Eye Drops", ["atropine eye drops","isopto atropine"], ["0.5%","1%"], "OPH", "mydriatic", "S4")
add("Prednisolone Eye Drops", ["prednisolone eye drops","pred forte","predsol eye"], ["0.5%","1%"], "OPH", "ophthalmic steroid", "S4")
add("Dexamethasone Eye Drops", ["dexamethasone eye drops","maxidex"], ["0.1%"], "OPH", "ophthalmic steroid", "S4")
add("Fluorescein Eye Strips", ["fluorescein","fluor-i-strip"], ["strips"], "OPH", "diagnostic", "S0")
add("Artificial Tears", ["artificial tears","tears naturale","systane","refresh tears"], ["drops"], "OPH", "lubricant", "S0")

# ══════════════════════════════════════════════════════════════
# DERMATOLOGICAL
# ══════════════════════════════════════════════════════════════
add("Hydrocortisone Cream", ["hydrocortisone cream","cortisone cream"], ["0.5%","1%"], "TOP", "topical steroid", "S1")
add("Betamethasone Cream", ["betamethasone cream","betnovate","celestoderm"], ["0.05%","0.1%"], "TOP", "topical steroid", "S3")
add("Betamethasone-Neomycin Cream", ["betnovate-n","betamethasone-neomycin"], ["0.1%/0.5%"], "TOP", "topical steroid", "S3")
add("Clobetasol Cream", ["clobetasol","dermovate","clobex"], ["0.05%"], "TOP", "topical steroid", "S4")
add("Mometasone Cream", ["mometasone","elocon"], ["0.1%"], "TOP", "topical steroid", "S3")
add("Emulsifying Ointment", ["emulsifying ointment","e45","aqueous cream base"], ["jar"], "TOP", "emollient", "S0")
add("Aqueous Cream", ["aqueous cream","aq cream"], ["jar"], "TOP", "emollient", "S0")
add("Calamine Lotion", ["calamine","calamine lotion"], ["lotion"], "TOP", "soothing agent", "S0")
add("Silver Sulfadiazine", ["silver sulfadiazine","flamazine","silvadene"], ["1%"], "TOP", "topical antibiotic", "S4")
add("Mupirocin Cream", ["mupirocin","bactroban"], ["2%"], "TOP", "topical antibiotic", "S4")
add("Fusidic Acid Cream", ["fusidic acid cream","fucidin cream"], ["2%"], "TOP", "topical antibiotic", "S4")
add("Aciclovir Cream", ["aciclovir cream","zovirax cream","acyclovir cream"], ["5%"], "TOP", "topical antiviral", "S2")
add("Benzoyl Peroxide", ["benzoyl peroxide","brevoxyl","benzac"], ["2.5%","5%","10%"], "TOP", "acne treatment", "S1")
add("Tretinoin Cream", ["tretinoin","retin-a","retinol cream"], ["0.025%","0.05%"], "TOP", "acne treatment", "S4")
add("Salicylic Acid", ["salicylic acid","duofilm"], ["2%","5%","10%"], "TOP", "keratolytic", "S0")
add("Coal Tar Preparation", ["coal tar","polytar","alphosyl"], ["5%","10%"], "TOP", "anti-psoriatic", "S0")
add("Dithranol", ["dithranol","anthralin","dithrocream"], ["0.1%","0.5%","1%"], "TOP", "anti-psoriatic", "S4")
add("Ketoconazole Shampoo", ["ketoconazole shampoo","nizoral shampoo"], ["2%"], "TOP", "antifungal shampoo", "S2")
add("Selenium Sulfide Shampoo", ["selenium sulfide","selsun"], ["2.5%"], "TOP", "antifungal shampoo", "S1")
add("Zinc Oxide Cream", ["zinc oxide","desitin","sudocrem"], ["20%","40%"], "TOP", "barrier cream", "S0")
add("Paraffin Gauze", ["jelonet","paraffin gauze","tulle gras"], ["dressing"], "TOP", "wound dressing", "S0")
add("Povidone Iodine", ["povidone iodine","betadine"], ["5%","10%"], "TOP", "antiseptic", "S0")
add("Chlorhexidine", ["chlorhexidine","savlon","hibiscrub","hibitane"], ["0.5%","1%","4%"], "TOP", "antiseptic", "S0")

# ══════════════════════════════════════════════════════════════
# ENT
# ══════════════════════════════════════════════════════════════
add("Chloramphenicol Ear Drops", ["chloramphenicol ear drops"], ["5%"], "OT", "otic antibiotic", "S4")
add("Ciprofloxacin Ear Drops", ["ciprofloxacin ear drops","ciprodex"], ["0.3%"], "OT", "otic antibiotic", "S4")
add("Hydrogen Peroxide Ear Drops", ["hydrogen peroxide ear drops","waxsol"], ["3%"], "OT", "cerumenolytic", "S0")
add("Oxymetazoline Nasal Spray", ["oxymetazoline","iliadin","afrin"], ["0.025%","0.05%"], "NAS", "nasal decongestant", "S2")
add("Xylometazoline Nasal", ["xylometazoline","otrivin","dristan nasal"], ["0.05%","0.1%"], "NAS", "nasal decongestant", "S2")
add("Budesonide Nasal Spray", ["budesonide nasal","rhinocort"], ["32mcg","64mcg"], "NAS", "nasal steroid", "S3")
add("Fluticasone Nasal Spray", ["fluticasone nasal","flixonase","flonase"], ["50mcg"], "NAS", "nasal steroid", "S3")
add("Mometasone Nasal Spray", ["mometasone nasal","nasonex"], ["50mcg"], "NAS", "nasal steroid", "S3")
add("Saline Nasal Spray", ["saline nasal spray","nasal saline","sterimar"], ["0.9%"], "NAS", "nasal rinse", "S0")

# ══════════════════════════════════════════════════════════════
# LOCAL ANAESTHETICS / ANAESTHESIA
# ══════════════════════════════════════════════════════════════
add("Lidocaine", ["lidocaine","lignocaine","xylocaine"], ["1%","2%"], "SC", "local anaesthetic", "S4")
add("Lidocaine with Adrenaline", ["lidocaine-adrenaline","xylocaine-adrenaline","lignocaine-epinephrine"], ["1%+1:100000","2%+1:80000"], "SC", "local anaesthetic", "S4")
add("Bupivacaine", ["bupivacaine","marcaine"], ["0.25%","0.5%"], "SC", "local anaesthetic", "S4")
add("Lidocaine Topical", ["emla","lidocaine cream","lignocaine gel"], ["2%","5%"], "TOP", "local anaesthetic", "S2")
add("Ketamine", ["ketamine","ketalar"], ["10mg/ml","50mg/ml"], "IV", "anaesthetic", "S5")
add("Propofol", ["propofol","diprivan"], ["10mg/ml","20mg/ml"], "IV", "anaesthetic", "S4")
add("Thiopental", ["thiopental","pentothal","thiopentone"], ["500mg","1g"], "IV", "anaesthetic", "S5")
add("Suxamethonium", ["suxamethonium","succinylcholine","anectine","scoline"], ["50mg/ml","100mg/2ml"], "IV", "muscle relaxant", "S4")
add("Atracurium", ["atracurium","tracrium"], ["10mg/ml"], "IV", "muscle relaxant", "S4")
add("Neostigmine", ["neostigmine","prostigmin"], ["0.5mg/ml","2.5mg/ml"], "IV", "anticholinesterase", "S4")
add("Atropine Pre-med", ["atropine","atropine sulfate"], ["0.5mg/ml","1mg/ml"], "IV", "anticholinergic", "S4")
add("Rocuronium", ["rocuronium","esmeron"], ["10mg/ml"], "IV", "muscle relaxant", "S4")

# ══════════════════════════════════════════════════════════════
# EMERGENCY / RESUSCITATION
# ══════════════════════════════════════════════════════════════
add("Adrenaline", ["adrenaline","epinephrine","epipen","jext"], ["1mg/ml","0.5mg/ml"], "IM", "emergency", "S4")
add("Adrenaline IV", ["adrenaline iv","epinephrine iv"], ["1mg/10ml"], "IV", "emergency", "S4")
add("Atropine Emergency", ["atropine emergency","atropine cardiac"], ["0.5mg/ml","1mg/ml"], "IV", "emergency", "S4")
add("Naloxone", ["naloxone","narcan"], ["0.4mg/ml","1mg/ml"], "IV", "opioid antagonist", "S4")
add("Flumazenil", ["flumazenil","anexate","romazicon"], ["0.5mg/5ml"], "IV", "benzodiazepine antagonist", "S4")
add("Sodium Bicarbonate", ["sodium bicarbonate","bicarb","nahco3"], ["8.4%","50ml"], "IV", "alkalinizer", "S4")
add("Glucose 50%", ["glucose 50%","dextrose 50%","d50w"], ["50ml"], "IV", "emergency", "S0")
add("Glucose 10%", ["glucose 10%","dextrose 10%","d10w"], ["500ml","1L"], "IV", "fluid", "S0")
add("Oxytocin", ["oxytocin","syntocinon","pitocin"], ["10IU/ml"], "IV", "obstetric", "S4")
add("Misoprostol", ["misoprostol","cytotec"], ["200mcg"], "PO", "obstetric", "S4")
add("Ergometrine", ["ergometrine","ergonovine","methergine"], ["0.2mg/ml","0.5mg/ml"], "IM", "obstetric", "S4")
add("Magnesium Sulfate Eclampsia", ["mgso4 eclampsia","magnesium sulfate 50%"], ["50%","10ml"], "IV", "eclampsia", "S4")
add("Phenytoin IV Emergency", ["phenytoin iv","dilantin iv"], ["250mg/5ml"], "IV", "anticonvulsant", "S4")
add("Normal Saline", ["normal saline","0.9% sodium chloride","ns","n/s"], ["100ml","200ml","500ml","1L"], "IV", "IV fluid", "S0")
add("Ringer's Lactate", ["ringers lactate","hartmanns","rl","lactated ringers"], ["500ml","1L"], "IV", "IV fluid", "S0")
add("Dextrose 5%", ["dextrose 5%","d5w","5% dextrose"], ["500ml","1L"], "IV", "IV fluid", "S0")
add("Dextrose-Saline", ["dextrose saline","d5ns","maintenance fluid"], ["500ml","1L"], "IV", "IV fluid", "S0")
add("Gelatin Colloid", ["gelofusine","haemaccel","gelatin colloid"], ["500ml"], "IV", "IV fluid", "S4")
add("Tranexamic Acid", ["tranexamic acid","cyklokapron","lysteda"], ["500mg","100mg/ml"], "IV", "antifibrinolytic", "S4")
add("Vitamin K", ["vitamin k","phytomenadione","konakion"], ["1mg/ml","10mg/ml"], "IV", "antidote", "S4")
add("Protamine Sulfate", ["protamine","protamine sulfate"], ["10mg/ml"], "IV", "heparin antidote", "S4")
add("Dantrolene", ["dantrolene","dantrium"], ["20mg"], "IV", "muscle relaxant", "S4")

# ══════════════════════════════════════════════════════════════
# ANTIHISTAMINES
# ══════════════════════════════════════════════════════════════
add("Chlorpheniramine", ["chlorpheniramine","piriton","chlorphenamine","allergex"], ["4mg","2mg/5ml"], "PO", "antihistamine", "S2")
add("Cetirizine", ["cetirizine","zyrtec","allertec"], ["10mg","5mg/5ml"], "PO", "antihistamine", "S2")
add("Loratadine", ["loratadine","clarityne","claritin","alavert"], ["10mg","5mg/5ml"], "PO", "antihistamine", "S2")
add("Fexofenadine", ["fexofenadine","telfast","allegra"], ["120mg","180mg"], "PO", "antihistamine", "S2")
add("Promethazine", ["promethazine","phenergan","avomine"], ["10mg","25mg","25mg/ml"], "PO", "antihistamine", "S3")
add("Diphenhydramine", ["diphenhydramine","benadryl"], ["25mg","50mg"], "PO", "antihistamine", "S2")

# ══════════════════════════════════════════════════════════════
# MUSCULOSKELETAL / GOUT
# ══════════════════════════════════════════════════════════════
add("Allopurinol", ["allopurinol","zyloric","zyloprim"], ["100mg","300mg"], "PO", "urate-lowering", "S3")
add("Colchicine", ["colchicine","colcine"], ["0.5mg","1mg"], "PO", "gout", "S4")
add("Methotrexate", ["methotrexate","mtx","trexall"], ["2.5mg","10mg","25mg/ml"], "PO", "immunosuppressant", "S4")
add("Orphenadrine", ["orphenadrine","disipal","norflex"], ["100mg"], "PO", "muscle relaxant", "S3")
add("Baclofen", ["baclofen","lioresal"], ["10mg","25mg"], "PO", "muscle relaxant", "S4")
add("Tizanidine", ["tizanidine","zanaflex","sirdalud"], ["2mg","4mg"], "PO", "muscle relaxant", "S4")
add("Chlorzoxazone", ["chlorzoxazone","parafon forte"], ["250mg","500mg"], "PO", "muscle relaxant", "S3")

# ══════════════════════════════════════════════════════════════
# UROLOGICAL
# ══════════════════════════════════════════════════════════════
add("Tamsulosin", ["tamsulosin","flomax","omnic"], ["0.4mg"], "PO", "alpha-blocker urological", "S3")
add("Finasteride", ["finasteride","proscar","propecia"], ["1mg","5mg"], "PO", "5-alpha reductase inhibitor", "S4")
add("Solifenacin", ["solifenacin","vesicare"], ["5mg","10mg"], "PO", "anticholinergic urological", "S3")
add("Oxybutynin", ["oxybutynin","ditropan"], ["2.5mg","5mg"], "PO", "anticholinergic urological", "S3")
add("Sildenafil", ["sildenafil","viagra","revatio"], ["25mg","50mg","100mg"], "PO", "PDE5 inhibitor", "S4")
add("Tadalafil", ["tadalafil","cialis"], ["5mg","10mg","20mg"], "PO", "PDE5 inhibitor", "S4")

# ══════════════════════════════════════════════════════════════
# IMMUNOSUPPRESSANTS
# ══════════════════════════════════════════════════════════════
add("Azathioprine", ["azathioprine","imuran"], ["50mg"], "PO", "immunosuppressant", "S4")
add("Cyclosporine", ["cyclosporine","ciclosporin","neoral","sandimmun"], ["25mg","50mg","100mg"], "PO", "immunosuppressant", "S4")
add("Mycophenolate", ["mycophenolate","cellcept","mmf"], ["250mg","500mg"], "PO", "immunosuppressant", "S4")
add("Tacrolimus", ["tacrolimus","prograf"], ["0.5mg","1mg","5mg"], "PO", "immunosuppressant", "S4")
add("Hydroxychloroquine", ["hydroxychloroquine","plaquenil"], ["200mg"], "PO", "immunomodulator", "S4")
add("Leflunomide", ["leflunomide","arava"], ["10mg","20mg"], "PO", "immunosuppressant", "S4")

# ══════════════════════════════════════════════════════════════
# VACCINES (commonly stocked)
# ══════════════════════════════════════════════════════════════
add("BCG Vaccine", ["bcg","bcg vaccine","tuberculosis vaccine"], ["vial"], "SC", "vaccine", "S4")
add("Hepatitis B Vaccine", ["hep b vaccine","engerix-b","hepatitis b"], ["vial"], "IM", "vaccine", "S4")
add("Measles Vaccine", ["measles vaccine","mmr","priorix"], ["vial"], "SC", "vaccine", "S4")
add("Tetanus Toxoid", ["tetanus toxoid","tt","adt","tetanus vaccine"], ["vial"], "IM", "vaccine", "S4")
add("Pneumococcal Vaccine", ["pneumococcal vaccine","prevnar","pneumovax","pcv"], ["vial"], "IM", "vaccine", "S4")
add("Influenza Vaccine", ["flu vaccine","influenza vaccine","fluvax"], ["0.5ml"], "IM", "vaccine", "S4")
add("Rotavirus Vaccine", ["rotavirus vaccine","rotarix","rotateq"], ["vial"], "PO", "vaccine", "S4")
add("HPV Vaccine", ["hpv vaccine","gardasil","cervarix"], ["0.5ml"], "IM", "vaccine", "S4")
add("Polio Vaccine OPV", ["opv","oral polio vaccine","polio drops"], ["vial"], "PO", "vaccine", "S4")
add("Pentavalent Vaccine", ["pentavalent","dtap-ipv-hib","pentaxim"], ["vial"], "IM", "vaccine", "S4")
add("COVID-19 Vaccine", ["covid vaccine","pfizer covid","comirnaty"], ["vial"], "IM", "vaccine", "S4")

# ══════════════════════════════════════════════════════════════
# MISCELLANEOUS
# ══════════════════════════════════════════════════════════════
add("Methotrexate Injectable", ["methotrexate injection","mtx injection"], ["25mg/ml"], "IM", "antineoplastic", "S4")
add("Cyclophosphamide", ["cyclophosphamide","endoxan","cytoxan"], ["50mg","500mg","1g"], "PO", "antineoplastic", "S4")
add("Cisplatin", ["cisplatin","platinol"], ["50mg","100mg"], "IV", "antineoplastic", "S4")
add("5-Fluorouracil", ["5-fu","fluorouracil","efudex"], ["500mg","250mg"], "IV", "antineoplastic", "S4")
add("Vincristine", ["vincristine","oncovin"], ["1mg","2mg"], "IV", "antineoplastic", "S4")
add("Doxorubicin", ["doxorubicin","adriamycin"], ["10mg","50mg"], "IV", "antineoplastic", "S4")

add("Ranitidine Injectable", ["ranitidine iv","zantac iv"], ["50mg/2ml"], "IV", "H2 blocker", "S4")
add("Probenecid", ["probenecid","benemid"], ["500mg"], "PO", "uricosuric", "S4")
add("Acetazolamide", ["acetazolamide","diamox"], ["250mg"], "PO", "carbonic anhydrase inhibitor", "S4")
add("Ephedrine", ["ephedrine"], ["30mg/ml"], "IV", "vasopressor", "S5")
add("Phenylephrine", ["phenylephrine","neo-synephrine"], ["10mg/ml"], "IV", "vasopressor", "S4")
add("Noradrenaline", ["noradrenaline","norepinephrine","levophed"], ["1mg/ml","4mg/4ml"], "IV", "vasopressor", "S4")
add("Vasopressin", ["vasopressin","pitressin"], ["20IU/ml"], "IV", "vasopressor", "S4")
add("Desmopressin", ["desmopressin","ddavp","minirin"], ["0.1mg","0.2mg","4mcg/ml"], "PO", "antidiuretic", "S4")

add("Chlorhexidine Mouthwash", ["chlorhexidine mouthwash","corsodyl","savacol"], ["0.2%"], "PO", "oral antiseptic", "S0")
add("Nystatin Oral Suspension", ["nystatin oral","mycostatin oral"], ["100000IU/ml"], "PO", "oral antifungal", "S2")
add("Miconazole Oral Gel", ["miconazole oral gel","daktarin oral gel"], ["2%"], "PO", "oral antifungal", "S2")

# ══════════════════════════════════════════════════════════════
# ADDITIONAL (to reach 500+)
# ══════════════════════════════════════════════════════════════
add("Gabapentin", ["gabapentin","neurontin"], ["100mg","300mg","400mg","600mg"], "PO", "neuropathic pain", "S4")
add("Pregabalin", ["pregabalin","lyrica"], ["75mg","150mg","300mg"], "PO", "neuropathic pain", "S5")
add("Duloxetine", ["duloxetine","cymbalta"], ["30mg","60mg"], "PO", "antidepressant", "S4")
add("Bupropion", ["bupropion","wellbutrin","zyban"], ["150mg","300mg"], "PO", "antidepressant", "S4")
add("Trazodone", ["trazodone","desyrel","molipaxin"], ["50mg","100mg","150mg"], "PO", "antidepressant", "S4")
add("Aripiprazole", ["aripiprazole","abilify"], ["5mg","10mg","15mg","30mg"], "PO", "antipsychotic", "S5")
add("Clozapine", ["clozapine","clozaril","leponex"], ["25mg","100mg"], "PO", "antipsychotic", "S5")
add("Flupentixol", ["flupentixol","fluanxol"], ["0.5mg","1mg","3mg"], "PO", "antipsychotic", "S5")
add("Fluphenazine Decanoate", ["fluphenazine","modecate"], ["25mg/ml"], "IM", "antipsychotic", "S5")
add("Zuclopenthixol Decanoate", ["zuclopenthixol","clopixol depot"], ["200mg/ml"], "IM", "antipsychotic", "S5")
add("Sumatriptan", ["sumatriptan","imigran","imitrex"], ["50mg","100mg"], "PO", "antimigraine", "S3")
add("Ergotamine", ["ergotamine","cafergot"], ["1mg"], "PO", "antimigraine", "S4")
add("Donepezil", ["donepezil","aricept"], ["5mg","10mg"], "PO", "anti-dementia", "S4")
add("Trihexyphenidyl", ["trihexyphenidyl","artane","benzhexol"], ["2mg","5mg"], "PO", "anticholinergic", "S4")
add("Levodopa-Carbidopa", ["levodopa","sinemet","madopar","carbidopa-levodopa"], ["100/25mg","250/25mg"], "PO", "antiparkinsonian", "S4")
add("Nifedipine Retard", ["nifedipine retard","adalat retard","adalat xl"], ["30mg","60mg","90mg"], "PO", "antihypertensive", "S3")
add("Enalapril-HCTZ", ["co-enalapril","enalapril-hctz"], ["20mg/12.5mg"], "PO", "antihypertensive", "S3")
add("Losartan-HCTZ", ["co-losartan","losartan-hctz","hyzaar"], ["50mg/12.5mg","100mg/25mg"], "PO", "antihypertensive", "S3")
add("Amlodipine-Valsartan", ["exforge","amlodipine-valsartan"], ["5/160mg","10/160mg"], "PO", "antihypertensive", "S3")
add("Atorvastatin-Ezetimibe", ["atozet","atorvastatin-ezetimibe"], ["10/10mg","20/10mg"], "PO", "lipid-lowering", "S3")
add("Metformin-Glimepiride", ["amaryl m","metformin-glimepiride"], ["500/1mg","500/2mg"], "PO", "antidiabetic", "S3")
add("Furosemide-Spironolactone", ["lasilactone","furosemide-spironolactone"], ["20/50mg"], "PO", "diuretic", "S3")
add("Sodium Valproate CR", ["epilim chrono","sodium valproate cr"], ["200mg","300mg","500mg"], "PO", "anticonvulsant", "S4")
add("Clobazam", ["clobazam","frisium","urbanyl"], ["10mg","20mg"], "PO", "anticonvulsant", "S5")
add("Vigabatrin", ["vigabatrin","sabril"], ["500mg"], "PO", "anticonvulsant", "S4")
add("Ethosuximide", ["ethosuximide","zarontin"], ["250mg"], "PO", "anticonvulsant", "S4")
add("Warfarin 3mg", ["warfarin 3mg","coumadin 3mg"], ["3mg"], "PO", "anticoagulant", "S4")
add("Ipratropium Nebuliser", ["ipratropium neb","atrovent neb"], ["250mcg/ml"], "INH", "bronchodilator", "S3")
add("Dextromethorphan", ["dextromethorphan","robitussin dm","benylin dm"], ["10mg/5ml","15mg"], "PO", "cough suppressant", "S1")
add("Codeine Linctus", ["codeine linctus","pholtex","benylin with codeine"], ["15mg/5ml"], "PO", "cough suppressant", "S5")
add("Guaifenesin", ["guaifenesin","mucinex","robitussin"], ["100mg/5ml","200mg"], "PO", "expectorant", "S1")
add("Bromhexine", ["bromhexine","bisolvon"], ["8mg","4mg/5ml"], "PO", "mucolytic", "S2")
add("Acetylcysteine", ["acetylcysteine","fluimucil","acc","nac"], ["200mg","600mg"], "PO", "mucolytic", "S2")
add("Levocetirizine", ["levocetirizine","xyzal"], ["5mg"], "PO", "antihistamine", "S2")
add("Desloratadine", ["desloratadine","aerius","clarinex"], ["5mg"], "PO", "antihistamine", "S2")
add("Montelukast Paediatric", ["montelukast chewable","singulair paediatric"], ["4mg","5mg"], "PO", "leukotriene antagonist", "S3")
add("Sodium Cromoglycate", ["sodium cromoglycate","intal","cromolyn"], ["5mg/puff"], "INH", "mast cell stabilizer", "S2")
add("Pseudoephedrine", ["pseudoephedrine","sudafed","actifed"], ["30mg","60mg"], "PO", "decongestant", "S2")

# Build final JSON
formulary = {
    "version": "2026.1",
    "country": "ZA",
    "source": "Based on South African Standard Treatment Guidelines and Essential Medicines List (STG/EML), National Department of Health",
    "drugs": drugs
}

output_path = "/Users/haohu/Documents/GitHub/emr/app/src/main/assets/formulary/za_formulary.json"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, "w") as f:
    json.dump(formulary, f, indent=2, ensure_ascii=False)

print(f"Generated {len(drugs)} drugs -> {output_path}")
