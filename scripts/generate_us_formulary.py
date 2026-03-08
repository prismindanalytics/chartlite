#!/usr/bin/env python3
"""Generate comprehensive US drug formulary JSON.
Based on FDA Orange Book, USP Drug Classification, and DEA Scheduling.
DEA Schedules: OTC (over-the-counter), Rx (prescription), C-V, C-IV, C-III, C-II
"""
import json, os

drugs = []
code = 1

def add(name, aliases, strengths, route, category, schedule):
    global code
    drugs.append({
        "code": f"US{code:04d}",
        "name": name,
        "aliases": aliases,
        "strengths": strengths,
        "defaultRoute": route,
        "category": category,
        "scheduleClass": schedule
    })
    code += 1

# ═══════════════════════════════════════════
# ANTIBIOTICS - Penicillins
# ═══════════════════════════════════════════
add("Amoxicillin",["amoxil","trimox","moxatag","amoxicillin"],["250mg","500mg","875mg","125mg/5ml","250mg/5ml"],"PO","antibiotic","Rx")
add("Amoxicillin-Clavulanate",["augmentin","augmentin es","augmentin xr"],["250/125mg","500/125mg","875/125mg","600/42.9mg/5ml"],"PO","antibiotic","Rx")
add("Ampicillin",["principen","ampicillin"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Ampicillin Injectable",["ampicillin injection"],["500mg","1g","2g"],"IV","antibiotic","Rx")
add("Penicillin V Potassium",["pen-vk","veetids","penicillin vk"],["250mg","500mg","125mg/5ml"],"PO","antibiotic","Rx")
add("Penicillin G Benzathine",["bicillin l-a","bicillin"],["1.2MU","2.4MU"],"IM","antibiotic","Rx")
add("Penicillin G Potassium",["pfizerpen","penicillin g"],["5MU","20MU"],"IV","antibiotic","Rx")
add("Nafcillin",["nallpen","nafcillin"],["1g","2g"],"IV","antibiotic","Rx")
add("Oxacillin",["oxacillin","bactocill"],["1g","2g"],"IV","antibiotic","Rx")
add("Dicloxacillin",["dicloxacillin","dynapen"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Piperacillin-Tazobactam",["zosyn","pip-tazo","piptaz"],["3.375g","4.5g"],"IV","antibiotic","Rx")
add("Ampicillin-Sulbactam",["unasyn","ampicillin-sulbactam"],["1.5g","3g"],"IV","antibiotic","Rx")
add("Ticarcillin-Clavulanate",["timentin"],["3.1g"],"IV","antibiotic","Rx")

# Cephalosporins
add("Cephalexin",["keflex","cephalexin","cefalexin"],["250mg","500mg","750mg"],"PO","antibiotic","Rx")
add("Cefadroxil",["duricef","cefadroxil"],["500mg","1g"],"PO","antibiotic","Rx")
add("Cefaclor",["ceclor","cefaclor"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Cefuroxime",["ceftin","zinacef"],["250mg","500mg","750mg","1.5g"],"PO","antibiotic","Rx")
add("Cefprozil",["cefzil","cefprozil"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Cefixime",["suprax","cefixime"],["200mg","400mg","100mg/5ml"],"PO","antibiotic","Rx")
add("Cefdinir",["omnicef","cefdinir"],["300mg","125mg/5ml"],"PO","antibiotic","Rx")
add("Cefpodoxime",["vantin","cefpodoxime"],["100mg","200mg"],"PO","antibiotic","Rx")
add("Ceftriaxone",["rocephin","ceftriaxone"],["250mg","1g","2g"],"IV","antibiotic","Rx")
add("Cefotaxime",["claforan","cefotaxime"],["1g","2g"],"IV","antibiotic","Rx")
add("Ceftazidime",["fortaz","tazicef"],["1g","2g"],"IV","antibiotic","Rx")
add("Cefepime",["maxipime","cefepime"],["1g","2g"],"IV","antibiotic","Rx")
add("Ceftaroline",["teflaro","ceftaroline"],["600mg"],"IV","antibiotic","Rx")
add("Cefazolin",["ancef","kefzol"],["1g","2g"],"IV","antibiotic","Rx")
add("Ceftazidime-Avibactam",["avycaz"],["2.5g"],"IV","antibiotic","Rx")
add("Ceftolozane-Tazobactam",["zerbaxa"],["1.5g","3g"],"IV","antibiotic","Rx")

# Fluoroquinolones
add("Ciprofloxacin",["cipro","ciprofloxacin"],["250mg","500mg","750mg"],"PO","antibiotic","Rx")
add("Ciprofloxacin Injectable",["cipro iv"],["200mg","400mg"],"IV","antibiotic","Rx")
add("Levofloxacin",["levaquin","levofloxacin"],["250mg","500mg","750mg"],"PO","antibiotic","Rx")
add("Moxifloxacin",["avelox","moxifloxacin"],["400mg"],"PO","antibiotic","Rx")
add("Delafloxacin",["baxdela"],["300mg","450mg"],"PO","antibiotic","Rx")

# Macrolides
add("Azithromycin",["zithromax","z-pack","zmax","azithromycin"],["250mg","500mg","200mg/5ml","1g"],"PO","antibiotic","Rx")
add("Erythromycin",["ery-tab","erythrocin","eryc","erythromycin"],["250mg","500mg","200mg/5ml"],"PO","antibiotic","Rx")
add("Clarithromycin",["biaxin","biaxin xl","clarithromycin"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Fidaxomicin",["dificid","fidaxomicin"],["200mg"],"PO","antibiotic","Rx")

# Tetracyclines
add("Doxycycline",["vibramycin","doryx","monodox","doxycycline","doxy"],["50mg","100mg","200mg"],"PO","antibiotic","Rx")
add("Tetracycline",["sumycin","tetracycline"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Minocycline",["minocin","solodyn","dynacin","minocycline"],["50mg","75mg","100mg"],"PO","antibiotic","Rx")
add("Doxycycline Hyclate",["vibramycin hyclate","doryx"],["20mg","50mg","100mg"],"PO","antibiotic","Rx")
add("Omadacycline",["nuzyra"],["150mg","300mg"],"PO","antibiotic","Rx")

# Aminoglycosides
add("Gentamicin",["garamycin","gentamicin"],["80mg/2ml","40mg/ml"],"IV","antibiotic","Rx")
add("Tobramycin",["nebcin","tobi","tobramycin"],["80mg/2ml","300mg/5ml"],"IV","antibiotic","Rx")
add("Amikacin",["amikin","amikacin"],["250mg/ml","500mg/2ml"],"IV","antibiotic","Rx")
add("Neomycin",["neo-fradin","neomycin"],["500mg"],"PO","antibiotic","Rx")
add("Plazomicin",["zemdri"],["500mg"],"IV","antibiotic","Rx")

# Other antibiotics
add("Metronidazole",["flagyl","metrogel","metronidazole","metro"],["250mg","500mg"],"PO","antibiotic","Rx")
add("Metronidazole Injectable",["flagyl iv"],["500mg/100ml"],"IV","antibiotic","Rx")
add("Trimethoprim-Sulfamethoxazole",["bactrim","bactrim ds","septra","tmp-smx","cotrimoxazole"],["400/80mg","800/160mg","200/40mg/5ml"],"PO","antibiotic","Rx")
add("Clindamycin",["cleocin","clindamycin","dalacin"],["150mg","300mg","450mg"],"PO","antibiotic","Rx")
add("Clindamycin Injectable",["cleocin phosphate"],["150mg/ml"],"IV","antibiotic","Rx")
add("Vancomycin Oral",["vancocin","vancomycin oral"],["125mg","250mg"],"PO","antibiotic","Rx")
add("Vancomycin Injectable",["vancocin iv","vancomycin iv"],["500mg","1g"],"IV","antibiotic","Rx")
add("Linezolid",["zyvox","linezolid"],["600mg"],"PO","antibiotic","Rx")
add("Daptomycin",["cubicin","daptomycin"],["500mg"],"IV","antibiotic","Rx")
add("Nitrofurantoin",["macrobid","macrodantin","nitrofurantoin"],["50mg","100mg"],"PO","antibiotic","Rx")
add("Fosfomycin",["monurol","fosfomycin"],["3g"],"PO","antibiotic","Rx")
add("Trimethoprim",["primsol","trimethoprim"],["100mg","200mg"],"PO","antibiotic","Rx")
add("Meropenem",["merrem","meropenem"],["500mg","1g"],"IV","antibiotic","Rx")
add("Imipenem-Cilastatin",["primaxin","imipenem"],["250mg","500mg"],"IV","antibiotic","Rx")
add("Ertapenem",["invanz","ertapenem"],["1g"],"IV","antibiotic","Rx")
add("Doripenem",["doribax","doripenem"],["500mg"],"IV","antibiotic","Rx")
add("Meropenem-Vaborbactam",["vabomere"],["2g/2g"],"IV","antibiotic","Rx")
add("Colistimethate",["coly-mycin m","colistin"],["150mg"],"IV","antibiotic","Rx")
add("Tigecycline",["tygacil","tigecycline"],["50mg"],"IV","antibiotic","Rx")
add("Quinupristin-Dalfopristin",["synercid"],["500mg"],"IV","antibiotic","Rx")
add("Tedizolid",["sivextro"],["200mg"],"PO","antibiotic","Rx")
add("Sulfasalazine",["azulfidine","sulfasalazine"],["500mg"],"PO","antibiotic","Rx")
add("Rifaximin",["xifaxan","rifaximin"],["200mg","550mg"],"PO","antibiotic","Rx")
add("Chloramphenicol",["chloromycetin","chloramphenicol"],["250mg"],"PO","antibiotic","Rx")

# ═══════════════════════════════════════════
# ANTIFUNGALS
# ═══════════════════════════════════════════
add("Fluconazole",["diflucan","fluconazole"],["50mg","100mg","150mg","200mg"],"PO","antifungal","Rx")
add("Itraconazole",["sporanox","itraconazole"],["100mg"],"PO","antifungal","Rx")
add("Voriconazole",["vfend","voriconazole"],["200mg","50mg"],"PO","antifungal","Rx")
add("Posaconazole",["noxafil","posaconazole"],["100mg","200mg/5ml"],"PO","antifungal","Rx")
add("Isavuconazonium",["cresemba","isavuconazole"],["186mg"],"PO","antifungal","Rx")
add("Ketoconazole",["nizoral","ketoconazole"],["200mg"],"PO","antifungal","Rx")
add("Nystatin Oral",["mycostatin","nystatin"],["100000U/ml"],"PO","antifungal","Rx")
add("Nystatin Topical",["nystatin cream","mycostatin cream"],["100000U/g"],"TOP","antifungal","Rx")
add("Clotrimazole",["lotrimin","mycelex","clotrimazole"],["1%","10mg troche"],"TOP","antifungal","OTC")
add("Miconazole",["monistat","micatin","miconazole"],["2%"],"TOP","antifungal","OTC")
add("Terbinafine",["lamisil","terbinafine"],["250mg","1%"],"PO","antifungal","Rx")
add("Griseofulvin",["grifulvin","griseofulvin"],["125mg","250mg","500mg"],"PO","antifungal","Rx")
add("Amphotericin B",["fungizone","ambisome","abelcet","amphotericin"],["50mg"],"IV","antifungal","Rx")
add("Caspofungin",["cancidas","caspofungin"],["50mg","70mg"],"IV","antifungal","Rx")
add("Micafungin",["mycamine","micafungin"],["50mg","100mg"],"IV","antifungal","Rx")
add("Anidulafungin",["eraxis","anidulafungin"],["100mg"],"IV","antifungal","Rx")
add("Flucytosine",["ancobon","flucytosine","5-fc"],["250mg","500mg"],"PO","antifungal","Rx")

# ═══════════════════════════════════════════
# ANTIVIRALS
# ═══════════════════════════════════════════
add("Acyclovir",["zovirax","acyclovir"],["200mg","400mg","800mg","5%"],"PO","antiviral","Rx")
add("Valacyclovir",["valtrex","valacyclovir"],["500mg","1g"],"PO","antiviral","Rx")
add("Famciclovir",["famvir","famciclovir"],["125mg","250mg","500mg"],"PO","antiviral","Rx")
add("Oseltamivir",["tamiflu","oseltamivir"],["30mg","45mg","75mg"],"PO","antiviral","Rx")
add("Baloxavir",["xofluza","baloxavir"],["20mg","40mg","80mg"],"PO","antiviral","Rx")
add("Ganciclovir",["cytovene","ganciclovir"],["250mg","500mg"],"IV","antiviral","Rx")
add("Valganciclovir",["valcyte","valganciclovir"],["450mg"],"PO","antiviral","Rx")
add("Remdesivir",["veklury","remdesivir"],["100mg"],"IV","antiviral","Rx")
add("Nirmatrelvir-Ritonavir",["paxlovid"],["150mg/100mg"],"PO","antiviral","Rx")
add("Molnupiravir",["lagevrio","molnupiravir"],["200mg"],"PO","antiviral","Rx")
add("Entecavir",["baraclude","entecavir"],["0.5mg","1mg"],"PO","antiviral","Rx")
add("Tenofovir Disoproxil",["viread","tenofovir","tdf"],["300mg"],"PO","antiviral","Rx")
add("Sofosbuvir-Velpatasvir",["epclusa"],["400mg/100mg"],"PO","antiviral","Rx")
add("Sofosbuvir-Ledipasvir",["harvoni"],["400mg/90mg"],"PO","antiviral","Rx")
add("Glecaprevir-Pibrentasvir",["mavyret"],["100mg/40mg"],"PO","antiviral","Rx")

# ═══════════════════════════════════════════
# ANALGESICS & NSAIDs
# ═══════════════════════════════════════════
add("Acetaminophen",["tylenol","paracetamol","acetaminophen","apap"],["325mg","500mg","650mg","160mg/5ml","1g"],"PO","analgesic","OTC")
add("Acetaminophen Suppository",["feverall","tylenol suppository"],["120mg","325mg","650mg"],"PR","analgesic","OTC")
add("Ibuprofen",["advil","motrin","ibuprofen"],["200mg","400mg","600mg","800mg","100mg/5ml"],"PO","NSAID","OTC")
add("Naproxen",["aleve","naprosyn","anaprox","naproxen"],["220mg","250mg","375mg","500mg"],"PO","NSAID","OTC")
add("Aspirin",["bayer","ecotrin","aspirin","asa","acetylsalicylic acid"],["81mg","325mg","500mg"],"PO","analgesic","OTC")
add("Diclofenac Oral",["voltaren","cataflam","diclofenac"],["25mg","50mg","75mg"],"PO","NSAID","Rx")
add("Diclofenac Topical",["voltaren gel","pennsaid","diclofenac gel"],["1%","1.5%","2%"],"TOP","NSAID","OTC")
add("Celecoxib",["celebrex","celecoxib"],["100mg","200mg","400mg"],"PO","NSAID","Rx")
add("Meloxicam",["mobic","meloxicam"],["7.5mg","15mg"],"PO","NSAID","Rx")
add("Indomethacin",["indocin","indomethacin"],["25mg","50mg","75mg"],"PO","NSAID","Rx")
add("Ketorolac",["toradol","ketorolac"],["10mg","15mg/ml","30mg/ml"],"PO","NSAID","Rx")
add("Piroxicam",["feldene","piroxicam"],["10mg","20mg"],"PO","NSAID","Rx")
add("Sulindac",["clinoril","sulindac"],["150mg","200mg"],"PO","NSAID","Rx")
add("Etodolac",["lodine","etodolac"],["200mg","300mg","400mg","500mg"],"PO","NSAID","Rx")
add("Nabumetone",["relafen","nabumetone"],["500mg","750mg"],"PO","NSAID","Rx")
add("Ketoprofen",["orudis","ketoprofen"],["50mg","75mg","100mg"],"PO","NSAID","Rx")
add("Diflunisal",["dolobid","diflunisal"],["250mg","500mg"],"PO","NSAID","Rx")

# Opioid Analgesics
add("Hydrocodone-Acetaminophen",["vicodin","norco","lortab","hydrocodone-apap"],["5/325mg","7.5/325mg","10/325mg"],"PO","opioid analgesic","C-II")
add("Oxycodone",["oxycontin","roxicodone","oxycodone"],["5mg","10mg","15mg","20mg","30mg","40mg","60mg","80mg"],"PO","opioid analgesic","C-II")
add("Oxycodone-Acetaminophen",["percocet","endocet","oxycodone-apap"],["2.5/325mg","5/325mg","7.5/325mg","10/325mg"],"PO","opioid analgesic","C-II")
add("Morphine Sulfate",["ms contin","kadian","avinza","morphine"],["15mg","30mg","60mg","100mg","200mg"],"PO","opioid analgesic","C-II")
add("Morphine Injectable",["morphine sulfate injection","duramorph"],["2mg/ml","4mg/ml","10mg/ml"],"IV","opioid analgesic","C-II")
add("Hydromorphone",["dilaudid","hydromorphone"],["2mg","4mg","8mg"],"PO","opioid analgesic","C-II")
add("Hydromorphone Injectable",["dilaudid injection"],["1mg/ml","2mg/ml","4mg/ml"],"IV","opioid analgesic","C-II")
add("Fentanyl Patch",["duragesic","fentanyl patch","fentanyl transdermal"],["12mcg/hr","25mcg/hr","50mcg/hr","75mcg/hr","100mcg/hr"],"TD","opioid analgesic","C-II")
add("Fentanyl Injectable",["sublimaze","fentanyl injection"],["50mcg/ml","100mcg/2ml"],"IV","opioid analgesic","C-II")
add("Fentanyl Lozenge",["actiq","fentanyl lozenge"],["200mcg","400mcg","600mcg","800mcg"],"SL","opioid analgesic","C-II")
add("Methadone",["dolophine","methadone","methadose"],["5mg","10mg","40mg"],"PO","opioid analgesic","C-II")
add("Codeine",["codeine sulfate","codeine"],["15mg","30mg","60mg"],"PO","opioid analgesic","C-II")
add("Acetaminophen-Codeine",["tylenol with codeine","tylenol #3"],["300/30mg","300/60mg"],"PO","opioid analgesic","C-III")
add("Tramadol",["ultram","ultram er","tramadol"],["50mg","100mg","200mg","300mg"],"PO","opioid analgesic","C-IV")
add("Tramadol-Acetaminophen",["ultracet"],["37.5/325mg"],"PO","opioid analgesic","C-IV")
add("Tapentadol",["nucynta","nucynta er","tapentadol"],["50mg","75mg","100mg"],"PO","opioid analgesic","C-II")
add("Buprenorphine",["subutex","butrans","buprenorphine"],["2mg","8mg","5mcg/hr","10mcg/hr","20mcg/hr"],"SL","opioid analgesic","C-III")
add("Buprenorphine-Naloxone",["suboxone","zubsolv"],["2/0.5mg","4/1mg","8/2mg","12/3mg"],"SL","opioid analgesic","C-III")
add("Naloxone",["narcan","naloxone"],["0.4mg/ml","2mg/ml","4mg nasal"],"IV","opioid antagonist","Rx")
add("Naltrexone",["vivitrol","revia","naltrexone"],["50mg","380mg"],"PO","opioid antagonist","Rx")
add("Meperidine",["demerol","meperidine","pethidine"],["50mg","100mg"],"PO","opioid analgesic","C-II")

# ═══════════════════════════════════════════
# ANTIHYPERTENSIVES - ACE Inhibitors
# ═══════════════════════════════════════════
add("Lisinopril",["zestril","prinivil","lisinopril"],["2.5mg","5mg","10mg","20mg","40mg"],"PO","antihypertensive","Rx")
add("Enalapril",["vasotec","enalapril","epaned"],["2.5mg","5mg","10mg","20mg"],"PO","antihypertensive","Rx")
add("Ramipril",["altace","ramipril"],["1.25mg","2.5mg","5mg","10mg"],"PO","antihypertensive","Rx")
add("Benazepril",["lotensin","benazepril"],["5mg","10mg","20mg","40mg"],"PO","antihypertensive","Rx")
add("Captopril",["capoten","captopril"],["12.5mg","25mg","50mg"],"PO","antihypertensive","Rx")
add("Fosinopril",["monopril","fosinopril"],["10mg","20mg","40mg"],"PO","antihypertensive","Rx")
add("Quinapril",["accupril","quinapril"],["5mg","10mg","20mg","40mg"],"PO","antihypertensive","Rx")
add("Perindopril",["aceon","perindopril"],["2mg","4mg","8mg"],"PO","antihypertensive","Rx")
add("Trandolapril",["mavik","trandolapril"],["1mg","2mg","4mg"],"PO","antihypertensive","Rx")
add("Moexipril",["univasc","moexipril"],["7.5mg","15mg"],"PO","antihypertensive","Rx")

# ARBs
add("Losartan",["cozaar","losartan"],["25mg","50mg","100mg"],"PO","antihypertensive","Rx")
add("Valsartan",["diovan","valsartan"],["40mg","80mg","160mg","320mg"],"PO","antihypertensive","Rx")
add("Irbesartan",["avapro","irbesartan"],["75mg","150mg","300mg"],"PO","antihypertensive","Rx")
add("Candesartan",["atacand","candesartan"],["4mg","8mg","16mg","32mg"],"PO","antihypertensive","Rx")
add("Telmisartan",["micardis","telmisartan"],["20mg","40mg","80mg"],"PO","antihypertensive","Rx")
add("Olmesartan",["benicar","olmesartan"],["5mg","20mg","40mg"],"PO","antihypertensive","Rx")
add("Azilsartan",["edarbi","azilsartan"],["40mg","80mg"],"PO","antihypertensive","Rx")
add("Sacubitril-Valsartan",["entresto","sacubitril-valsartan"],["24/26mg","49/51mg","97/103mg"],"PO","antihypertensive","Rx")

# CCBs
add("Amlodipine",["norvasc","amlodipine"],["2.5mg","5mg","10mg"],"PO","antihypertensive","Rx")
add("Nifedipine",["procardia","adalat","nifedipine"],["10mg","20mg","30mg","60mg","90mg"],"PO","antihypertensive","Rx")
add("Diltiazem",["cardizem","tiazac","dilacor","diltiazem"],["30mg","60mg","90mg","120mg","180mg","240mg","300mg","360mg"],"PO","antihypertensive","Rx")
add("Verapamil",["calan","isoptin","verelan","verapamil"],["40mg","80mg","120mg","180mg","240mg","360mg"],"PO","antihypertensive","Rx")
add("Felodipine",["plendil","felodipine"],["2.5mg","5mg","10mg"],"PO","antihypertensive","Rx")
add("Nicardipine",["cardene","nicardipine"],["20mg","30mg"],"PO","antihypertensive","Rx")
add("Nisoldipine",["sular","nisoldipine"],["8.5mg","17mg","25.5mg","34mg"],"PO","antihypertensive","Rx")

# Beta Blockers
add("Metoprolol Tartrate",["lopressor","metoprolol tartrate"],["25mg","50mg","100mg"],"PO","beta blocker","Rx")
add("Metoprolol Succinate",["toprol xl","metoprolol succinate"],["25mg","50mg","100mg","200mg"],"PO","beta blocker","Rx")
add("Atenolol",["tenormin","atenolol"],["25mg","50mg","100mg"],"PO","beta blocker","Rx")
add("Propranolol",["inderal","inderal la","propranolol"],["10mg","20mg","40mg","60mg","80mg","120mg","160mg"],"PO","beta blocker","Rx")
add("Carvedilol",["coreg","coreg cr","carvedilol"],["3.125mg","6.25mg","12.5mg","25mg"],"PO","beta blocker","Rx")
add("Bisoprolol",["zebeta","bisoprolol"],["5mg","10mg"],"PO","beta blocker","Rx")
add("Nebivolol",["bystolic","nebivolol"],["2.5mg","5mg","10mg","20mg"],"PO","beta blocker","Rx")
add("Labetalol",["trandate","labetalol"],["100mg","200mg","300mg"],"PO","beta blocker","Rx")
add("Nadolol",["corgard","nadolol"],["20mg","40mg","80mg"],"PO","beta blocker","Rx")
add("Sotalol",["betapace","sotalol"],["80mg","120mg","160mg","240mg"],"PO","beta blocker","Rx")
add("Pindolol",["visken","pindolol"],["5mg","10mg"],"PO","beta blocker","Rx")
add("Acebutolol",["sectral","acebutolol"],["200mg","400mg"],"PO","beta blocker","Rx")

# Diuretics
add("Hydrochlorothiazide",["microzide","hctz","hydrochlorothiazide"],["12.5mg","25mg","50mg"],"PO","diuretic","Rx")
add("Chlorthalidone",["thalitone","chlorthalidone"],["12.5mg","25mg","50mg"],"PO","diuretic","Rx")
add("Indapamide",["lozol","indapamide"],["1.25mg","2.5mg"],"PO","diuretic","Rx")
add("Furosemide",["lasix","furosemide"],["20mg","40mg","80mg","10mg/ml"],"PO","diuretic","Rx")
add("Furosemide Injectable",["lasix injection"],["10mg/ml","20mg","40mg","100mg"],"IV","diuretic","Rx")
add("Bumetanide",["bumex","bumetanide"],["0.5mg","1mg","2mg"],"PO","diuretic","Rx")
add("Torsemide",["demadex","torsemide"],["5mg","10mg","20mg","100mg"],"PO","diuretic","Rx")
add("Spironolactone",["aldactone","spironolactone"],["25mg","50mg","100mg"],"PO","diuretic","Rx")
add("Eplerenone",["inspra","eplerenone"],["25mg","50mg"],"PO","diuretic","Rx")
add("Triamterene-HCTZ",["dyazide","maxzide","triamterene-hctz"],["37.5/25mg","75/50mg"],"PO","diuretic","Rx")
add("Amiloride",["midamor","amiloride"],["5mg"],"PO","diuretic","Rx")
add("Metolazone",["zaroxolyn","metolazone"],["2.5mg","5mg","10mg"],"PO","diuretic","Rx")
add("Acetazolamide",["diamox","acetazolamide"],["125mg","250mg","500mg"],"PO","diuretic","Rx")
add("Mannitol",["osmitrol","mannitol"],["20%","25%"],"IV","diuretic","Rx")

# Other antihypertensives
add("Clonidine",["catapres","kapvay","clonidine"],["0.1mg","0.2mg","0.3mg","0.1mg/24hr","0.2mg/24hr","0.3mg/24hr"],"PO","antihypertensive","Rx")
add("Hydralazine",["apresoline","hydralazine"],["10mg","25mg","50mg","100mg"],"PO","antihypertensive","Rx")
add("Minoxidil Oral",["loniten","minoxidil"],["2.5mg","10mg"],"PO","antihypertensive","Rx")
add("Prazosin",["minipress","prazosin"],["1mg","2mg","5mg"],"PO","alpha blocker","Rx")
add("Doxazosin",["cardura","doxazosin"],["1mg","2mg","4mg","8mg"],"PO","alpha blocker","Rx")
add("Terazosin",["hytrin","terazosin"],["1mg","2mg","5mg","10mg"],"PO","alpha blocker","Rx")

# ═══════════════════════════════════════════
# DIABETES MEDICATIONS
# ═══════════════════════════════════════════
add("Metformin",["glucophage","glucophage xr","metformin","riomet"],["500mg","850mg","1000mg","500mg/5ml"],"PO","antidiabetic","Rx")
add("Glipizide",["glucotrol","glucotrol xl","glipizide"],["5mg","10mg"],"PO","antidiabetic","Rx")
add("Glyburide",["diabeta","micronase","glynase","glyburide"],["1.25mg","2.5mg","5mg"],"PO","antidiabetic","Rx")
add("Glimepiride",["amaryl","glimepiride"],["1mg","2mg","4mg"],"PO","antidiabetic","Rx")
add("Pioglitazone",["actos","pioglitazone"],["15mg","30mg","45mg"],"PO","antidiabetic","Rx")
add("Sitagliptin",["januvia","sitagliptin"],["25mg","50mg","100mg"],"PO","antidiabetic","Rx")
add("Linagliptin",["tradjenta","linagliptin"],["5mg"],"PO","antidiabetic","Rx")
add("Saxagliptin",["onglyza","saxagliptin"],["2.5mg","5mg"],"PO","antidiabetic","Rx")
add("Alogliptin",["nesina","alogliptin"],["6.25mg","12.5mg","25mg"],"PO","antidiabetic","Rx")
add("Empagliflozin",["jardiance","empagliflozin"],["10mg","25mg"],"PO","antidiabetic","Rx")
add("Dapagliflozin",["farxiga","dapagliflozin"],["5mg","10mg"],"PO","antidiabetic","Rx")
add("Canagliflozin",["invokana","canagliflozin"],["100mg","300mg"],"PO","antidiabetic","Rx")
add("Ertugliflozin",["steglatro","ertugliflozin"],["5mg","15mg"],"PO","antidiabetic","Rx")
add("Liraglutide",["victoza","saxenda","liraglutide"],["0.6mg","1.2mg","1.8mg"],"SC","antidiabetic","Rx")
add("Semaglutide Injectable",["ozempic","wegovy","semaglutide"],["0.25mg","0.5mg","1mg","2mg","2.4mg"],"SC","antidiabetic","Rx")
add("Semaglutide Oral",["rybelsus","oral semaglutide"],["3mg","7mg","14mg"],"PO","antidiabetic","Rx")
add("Dulaglutide",["trulicity","dulaglutide"],["0.75mg","1.5mg","3mg","4.5mg"],"SC","antidiabetic","Rx")
add("Exenatide",["byetta","bydureon","exenatide"],["5mcg","10mcg","2mg"],"SC","antidiabetic","Rx")
add("Tirzepatide",["mounjaro","zepbound","tirzepatide"],["2.5mg","5mg","7.5mg","10mg","12.5mg","15mg"],"SC","antidiabetic","Rx")
add("Acarbose",["precose","acarbose"],["25mg","50mg","100mg"],"PO","antidiabetic","Rx")
add("Repaglinide",["prandin","repaglinide"],["0.5mg","1mg","2mg"],"PO","antidiabetic","Rx")
add("Nateglinide",["starlix","nateglinide"],["60mg","120mg"],"PO","antidiabetic","Rx")

# Insulins
add("Insulin Regular",["humulin r","novolin r","regular insulin"],["100U/ml"],"SC","insulin","Rx")
add("Insulin NPH",["humulin n","novolin n","nph insulin"],["100U/ml"],"SC","insulin","Rx")
add("Insulin 70/30",["humulin 70/30","novolin 70/30"],["100U/ml"],"SC","insulin","Rx")
add("Insulin Lispro",["humalog","admelog","insulin lispro"],["100U/ml","200U/ml"],"SC","insulin","Rx")
add("Insulin Aspart",["novolog","fiasp","insulin aspart"],["100U/ml"],"SC","insulin","Rx")
add("Insulin Glulisine",["apidra","insulin glulisine"],["100U/ml"],"SC","insulin","Rx")
add("Insulin Glargine",["lantus","basaglar","semglee","toujeo","insulin glargine"],["100U/ml","300U/ml"],"SC","insulin","Rx")
add("Insulin Detemir",["levemir","insulin detemir"],["100U/ml"],"SC","insulin","Rx")
add("Insulin Degludec",["tresiba","insulin degludec"],["100U/ml","200U/ml"],"SC","insulin","Rx")

# ═══════════════════════════════════════════
# LIPID-LOWERING AGENTS
# ═══════════════════════════════════════════
add("Atorvastatin",["lipitor","atorvastatin"],["10mg","20mg","40mg","80mg"],"PO","statin","Rx")
add("Rosuvastatin",["crestor","rosuvastatin"],["5mg","10mg","20mg","40mg"],"PO","statin","Rx")
add("Simvastatin",["zocor","simvastatin"],["5mg","10mg","20mg","40mg","80mg"],"PO","statin","Rx")
add("Pravastatin",["pravachol","pravastatin"],["10mg","20mg","40mg","80mg"],"PO","statin","Rx")
add("Lovastatin",["mevacor","altoprev","lovastatin"],["10mg","20mg","40mg"],"PO","statin","Rx")
add("Fluvastatin",["lescol","fluvastatin"],["20mg","40mg","80mg"],"PO","statin","Rx")
add("Pitavastatin",["livalo","zypitamag","pitavastatin"],["1mg","2mg","4mg"],"PO","statin","Rx")
add("Ezetimibe",["zetia","ezetimibe"],["10mg"],"PO","lipid-lowering","Rx")
add("Ezetimibe-Simvastatin",["vytorin"],["10/10mg","10/20mg","10/40mg","10/80mg"],"PO","lipid-lowering","Rx")
add("Fenofibrate",["tricor","trilipix","antara","fenofibrate"],["48mg","54mg","145mg","160mg"],"PO","lipid-lowering","Rx")
add("Gemfibrozil",["lopid","gemfibrozil"],["600mg"],"PO","lipid-lowering","Rx")
add("Omega-3-Acid Ethyl Esters",["lovaza","vascepa","icosapent ethyl","omega-3"],["1g","2g"],"PO","lipid-lowering","Rx")
add("Alirocumab",["praluent","alirocumab"],["75mg","150mg"],"SC","lipid-lowering","Rx")
add("Evolocumab",["repatha","evolocumab"],["140mg","420mg"],"SC","lipid-lowering","Rx")
add("Inclisiran",["leqvio","inclisiran"],["284mg"],"SC","lipid-lowering","Rx")
add("Bempedoic Acid",["nexletol","bempedoic acid"],["180mg"],"PO","lipid-lowering","Rx")
add("Cholestyramine",["questran","prevalite","cholestyramine"],["4g"],"PO","lipid-lowering","Rx")
add("Niacin",["niaspan","slo-niacin","niacin"],["500mg","750mg","1000mg"],"PO","lipid-lowering","Rx")

# ═══════════════════════════════════════════
# ANTICOAGULANTS & ANTIPLATELETS
# ═══════════════════════════════════════════
add("Warfarin",["coumadin","jantoven","warfarin"],["1mg","2mg","2.5mg","3mg","4mg","5mg","6mg","7.5mg","10mg"],"PO","anticoagulant","Rx")
add("Enoxaparin",["lovenox","enoxaparin"],["30mg","40mg","60mg","80mg","100mg","120mg","150mg"],"SC","anticoagulant","Rx")
add("Heparin",["heparin sodium","heparin"],["1000U/ml","5000U/ml","10000U/ml"],"IV","anticoagulant","Rx")
add("Apixaban",["eliquis","apixaban"],["2.5mg","5mg"],"PO","anticoagulant","Rx")
add("Rivaroxaban",["xarelto","rivaroxaban"],["2.5mg","10mg","15mg","20mg"],"PO","anticoagulant","Rx")
add("Dabigatran",["pradaxa","dabigatran"],["75mg","110mg","150mg"],"PO","anticoagulant","Rx")
add("Edoxaban",["savaysa","edoxaban"],["15mg","30mg","60mg"],"PO","anticoagulant","Rx")
add("Clopidogrel",["plavix","clopidogrel"],["75mg","300mg"],"PO","antiplatelet","Rx")
add("Ticagrelor",["brilinta","ticagrelor"],["60mg","90mg"],"PO","antiplatelet","Rx")
add("Prasugrel",["effient","prasugrel"],["5mg","10mg"],"PO","antiplatelet","Rx")
add("Dipyridamole-Aspirin",["aggrenox"],["200/25mg"],"PO","antiplatelet","Rx")
add("Fondaparinux",["arixtra","fondaparinux"],["2.5mg","5mg","7.5mg","10mg"],"SC","anticoagulant","Rx")
add("Bivalirudin",["angiomax","bivalirudin"],["250mg"],"IV","anticoagulant","Rx")

# ═══════════════════════════════════════════
# RESPIRATORY
# ═══════════════════════════════════════════
add("Albuterol Inhaler",["proventil","ventolin","proair","albuterol"],["90mcg/inh"],"INH","bronchodilator","Rx")
add("Albuterol Nebulizer",["accuneb","albuterol nebulizer"],["0.63mg/3ml","1.25mg/3ml","2.5mg/3ml"],"NEB","bronchodilator","Rx")
add("Levalbuterol",["xopenex","levalbuterol"],["0.31mg/3ml","0.63mg/3ml","1.25mg/3ml"],"NEB","bronchodilator","Rx")
add("Ipratropium",["atrovent","ipratropium"],["17mcg/inh","0.02%","0.5mg/2.5ml"],"INH","bronchodilator","Rx")
add("Ipratropium-Albuterol",["combivent","duoneb"],["20/100mcg/inh","0.5/2.5mg/3ml"],"INH","bronchodilator","Rx")
add("Tiotropium",["spiriva","spiriva respimat","tiotropium"],["18mcg","1.25mcg/inh","2.5mcg/inh"],"INH","bronchodilator","Rx")
add("Umeclidinium",["incruse ellipta"],["62.5mcg"],"INH","bronchodilator","Rx")
add("Fluticasone Inhaler",["flovent","arnuity","fluticasone"],["44mcg","110mcg","220mcg"],"INH","corticosteroid","Rx")
add("Budesonide Inhaler",["pulmicort","pulmicort flexhaler","budesonide"],["90mcg","180mcg","0.25mg/2ml","0.5mg/2ml","1mg/2ml"],"INH","corticosteroid","Rx")
add("Beclomethasone Inhaler",["qvar","beclomethasone"],["40mcg","80mcg"],"INH","corticosteroid","Rx")
add("Mometasone Inhaler",["asmanex","mometasone"],["110mcg","220mcg"],"INH","corticosteroid","Rx")
add("Fluticasone-Salmeterol",["advair","airduo","wixela","fluticasone-salmeterol"],["100/50mcg","250/50mcg","500/50mcg"],"INH","combination inhaler","Rx")
add("Budesonide-Formoterol",["symbicort","breyna","budesonide-formoterol"],["80/4.5mcg","160/4.5mcg"],"INH","combination inhaler","Rx")
add("Fluticasone-Vilanterol",["breo ellipta"],["100/25mcg","200/25mcg"],"INH","combination inhaler","Rx")
add("Umeclidinium-Vilanterol",["anoro ellipta"],["62.5/25mcg"],"INH","combination inhaler","Rx")
add("Fluticasone-Umeclidinium-Vilanterol",["trelegy ellipta"],["100/62.5/25mcg","200/62.5/25mcg"],"INH","combination inhaler","Rx")
add("Montelukast",["singulair","montelukast"],["4mg","5mg","10mg"],"PO","leukotriene modifier","Rx")
add("Zafirlukast",["accolate","zafirlukast"],["10mg","20mg"],"PO","leukotriene modifier","Rx")
add("Theophylline",["theo-24","theochron","elixophyllin","theophylline"],["100mg","200mg","300mg","400mg","450mg","600mg"],"PO","bronchodilator","Rx")
add("Roflumilast",["daliresp","roflumilast"],["500mcg"],"PO","PDE4 inhibitor","Rx")
add("Omalizumab",["xolair","omalizumab"],["75mg","150mg"],"SC","biologic","Rx")
add("Dupilumab",["dupixent","dupilumab"],["200mg","300mg"],"SC","biologic","Rx")
add("Benzonatate",["tessalon","benzonatate"],["100mg","200mg"],"PO","antitussive","Rx")
add("Dextromethorphan-Guaifenesin",["mucinex dm","robitussin dm"],["30/600mg","20/400mg"],"PO","antitussive","OTC")
add("Guaifenesin",["mucinex","robitussin","guaifenesin"],["200mg","400mg","600mg","1200mg"],"PO","expectorant","OTC")
add("Pseudoephedrine",["sudafed","pseudoephedrine"],["30mg","60mg","120mg","240mg"],"PO","decongestant","OTC")

# ═══════════════════════════════════════════
# GASTROINTESTINAL
# ═══════════════════════════════════════════
add("Omeprazole",["prilosec","omeprazole"],["10mg","20mg","40mg"],"PO","proton pump inhibitor","OTC")
add("Esomeprazole",["nexium","esomeprazole"],["20mg","40mg"],"PO","proton pump inhibitor","OTC")
add("Lansoprazole",["prevacid","lansoprazole"],["15mg","30mg"],"PO","proton pump inhibitor","OTC")
add("Pantoprazole",["protonix","pantoprazole"],["20mg","40mg"],"PO","proton pump inhibitor","Rx")
add("Rabeprazole",["aciphex","rabeprazole"],["20mg"],"PO","proton pump inhibitor","Rx")
add("Dexlansoprazole",["dexilant","dexlansoprazole"],["30mg","60mg"],"PO","proton pump inhibitor","Rx")
add("Famotidine",["pepcid","famotidine"],["10mg","20mg","40mg"],"PO","H2 blocker","OTC")
add("Ranitidine",["zantac","ranitidine"],["75mg","150mg","300mg"],"PO","H2 blocker","OTC")
add("Sucralfate",["carafate","sucralfate"],["1g"],"PO","mucosal protectant","Rx")
add("Misoprostol",["cytotec","misoprostol"],["100mcg","200mcg"],"PO","prostaglandin","Rx")
add("Metoclopramide",["reglan","metoclopramide"],["5mg","10mg"],"PO","prokinetic","Rx")
add("Ondansetron",["zofran","ondansetron"],["4mg","8mg","4mg/5ml","4mg odt"],"PO","antiemetic","Rx")
add("Promethazine",["phenergan","promethazine"],["12.5mg","25mg","50mg","25mg/ml"],"PO","antiemetic","Rx")
add("Prochlorperazine",["compazine","prochlorperazine"],["5mg","10mg","25mg"],"PO","antiemetic","Rx")
add("Granisetron",["kytril","sancuso","granisetron"],["1mg","3.1mg/24hr"],"PO","antiemetic","Rx")
add("Loperamide",["imodium","loperamide"],["2mg"],"PO","antidiarrheal","OTC")
add("Diphenoxylate-Atropine",["lomotil","diphenoxylate-atropine"],["2.5/0.025mg"],"PO","antidiarrheal","C-V")
add("Bismuth Subsalicylate",["pepto-bismol","kaopectate","bismuth subsalicylate"],["262mg","525mg"],"PO","antidiarrheal","OTC")
add("Polyethylene Glycol",["miralax","golytely","peg 3350"],["17g","255g"],"PO","laxative","OTC")
add("Lactulose",["enulose","kristalose","lactulose"],["10g/15ml"],"PO","laxative","Rx")
add("Docusate",["colace","docusate","dulcolax stool softener"],["50mg","100mg","250mg"],"PO","stool softener","OTC")
add("Bisacodyl",["dulcolax","bisacodyl"],["5mg","10mg"],"PO","laxative","OTC")
add("Senna",["senokot","senna","ex-lax"],["8.6mg","15mg","17.2mg"],"PO","laxative","OTC")
add("Psyllium",["metamucil","psyllium","konsyl"],["3.4g"],"PO","laxative","OTC")
add("Linaclotide",["linzess","linaclotide"],["72mcg","145mcg","290mcg"],"PO","GI motility","Rx")
add("Lubiprostone",["amitiza","lubiprostone"],["8mcg","24mcg"],"PO","GI motility","Rx")
add("Mesalamine",["asacol","lialda","apriso","pentasa","delzicol","mesalamine"],["400mg","500mg","800mg","1.2g"],"PO","aminosalicylate","Rx")
add("Sulfasalazine GI",["azulfidine","sulfasalazine"],["500mg"],"PO","aminosalicylate","Rx")
add("Ursodiol",["actigall","urso","ursodiol"],["250mg","300mg","500mg"],"PO","bile acid","Rx")
add("Dicyclomine",["bentyl","dicyclomine"],["10mg","20mg"],"PO","antispasmodic","Rx")
add("Hyoscyamine",["levsin","anaspaz","hyoscyamine"],["0.125mg","0.375mg"],"PO","antispasmodic","Rx")
add("Simethicone",["gas-x","mylicon","phazyme","simethicone"],["40mg","80mg","125mg","180mg"],"PO","antiflatulent","OTC")
add("Calcium Carbonate",["tums","rolaids","calcium carbonate"],["500mg","750mg","1000mg"],"PO","antacid","OTC")
add("Aluminum-Magnesium Hydroxide",["maalox","mylanta"],["200mg/200mg/5ml"],"PO","antacid","OTC")

# ═══════════════════════════════════════════
# PSYCHIATRIC - Antidepressants
# ═══════════════════════════════════════════
add("Sertraline",["zoloft","sertraline"],["25mg","50mg","100mg"],"PO","SSRI","Rx")
add("Fluoxetine",["prozac","sarafem","fluoxetine"],["10mg","20mg","40mg","60mg"],"PO","SSRI","Rx")
add("Escitalopram",["lexapro","escitalopram"],["5mg","10mg","20mg"],"PO","SSRI","Rx")
add("Citalopram",["celexa","citalopram"],["10mg","20mg","40mg"],"PO","SSRI","Rx")
add("Paroxetine",["paxil","paxil cr","paroxetine"],["10mg","20mg","30mg","40mg"],"PO","SSRI","Rx")
add("Fluvoxamine",["luvox","fluvoxamine"],["25mg","50mg","100mg"],"PO","SSRI","Rx")
add("Venlafaxine",["effexor","effexor xr","venlafaxine"],["37.5mg","75mg","150mg","225mg"],"PO","SNRI","Rx")
add("Duloxetine",["cymbalta","duloxetine"],["20mg","30mg","60mg"],"PO","SNRI","Rx")
add("Desvenlafaxine",["pristiq","desvenlafaxine"],["25mg","50mg","100mg"],"PO","SNRI","Rx")
add("Milnacipran",["savella","milnacipran"],["12.5mg","25mg","50mg"],"PO","SNRI","Rx")
add("Levomilnacipran",["fetzima"],["20mg","40mg","80mg","120mg"],"PO","SNRI","Rx")
add("Bupropion",["wellbutrin","wellbutrin xl","zyban","bupropion"],["75mg","100mg","150mg","300mg"],"PO","antidepressant","Rx")
add("Mirtazapine",["remeron","mirtazapine"],["7.5mg","15mg","30mg","45mg"],"PO","antidepressant","Rx")
add("Trazodone",["desyrel","oleptro","trazodone"],["50mg","100mg","150mg","300mg"],"PO","antidepressant","Rx")
add("Nefazodone",["nefazodone"],["50mg","100mg","150mg","200mg","250mg"],"PO","antidepressant","Rx")
add("Amitriptyline",["elavil","amitriptyline"],["10mg","25mg","50mg","75mg","100mg","150mg"],"PO","tricyclic","Rx")
add("Nortriptyline",["pamelor","aventyl","nortriptyline"],["10mg","25mg","50mg","75mg"],"PO","tricyclic","Rx")
add("Imipramine",["tofranil","imipramine"],["10mg","25mg","50mg","75mg"],"PO","tricyclic","Rx")
add("Desipramine",["norpramin","desipramine"],["10mg","25mg","50mg","75mg","100mg","150mg"],"PO","tricyclic","Rx")
add("Doxepin",["sinequan","silenor","doxepin"],["3mg","6mg","10mg","25mg","50mg","75mg","100mg","150mg"],"PO","tricyclic","Rx")
add("Clomipramine",["anafranil","clomipramine"],["25mg","50mg","75mg"],"PO","tricyclic","Rx")
add("Phenelzine",["nardil","phenelzine"],["15mg"],"PO","MAOI","Rx")
add("Tranylcypromine",["parnate","tranylcypromine"],["10mg"],"PO","MAOI","Rx")
add("Selegiline Patch",["emsam","selegiline transdermal"],["6mg/24hr","9mg/24hr","12mg/24hr"],"TD","MAOI","Rx")
add("Vilazodone",["viibryd","vilazodone"],["10mg","20mg","40mg"],"PO","antidepressant","Rx")
add("Vortioxetine",["trintellix","vortioxetine"],["5mg","10mg","20mg"],"PO","antidepressant","Rx")
add("Esketamine",["spravato","esketamine"],["28mg","56mg","84mg"],"NASAL","antidepressant","C-III")

# Anxiolytics & Sedatives
add("Alprazolam",["xanax","xanax xr","alprazolam"],["0.25mg","0.5mg","1mg","2mg"],"PO","benzodiazepine","C-IV")
add("Lorazepam",["ativan","lorazepam"],["0.5mg","1mg","2mg"],"PO","benzodiazepine","C-IV")
add("Clonazepam",["klonopin","clonazepam"],["0.5mg","1mg","2mg"],"PO","benzodiazepine","C-IV")
add("Diazepam",["valium","diazepam"],["2mg","5mg","10mg"],"PO","benzodiazepine","C-IV")
add("Midazolam",["versed","midazolam"],["2mg/ml","5mg/ml"],"IV","benzodiazepine","C-IV")
add("Temazepam",["restoril","temazepam"],["7.5mg","15mg","22.5mg","30mg"],"PO","benzodiazepine","C-IV")
add("Triazolam",["halcion","triazolam"],["0.125mg","0.25mg"],"PO","benzodiazepine","C-IV")
add("Chlordiazepoxide",["librium","chlordiazepoxide"],["5mg","10mg","25mg"],"PO","benzodiazepine","C-IV")
add("Oxazepam",["serax","oxazepam"],["10mg","15mg","30mg"],"PO","benzodiazepine","C-IV")
add("Buspirone",["buspar","buspirone"],["5mg","7.5mg","10mg","15mg","30mg"],"PO","anxiolytic","Rx")
add("Hydroxyzine",["vistaril","atarax","hydroxyzine"],["10mg","25mg","50mg"],"PO","anxiolytic","Rx")
add("Zolpidem",["ambien","ambien cr","zolpidem"],["5mg","6.25mg","10mg","12.5mg"],"PO","sedative","C-IV")
add("Eszopiclone",["lunesta","eszopiclone"],["1mg","2mg","3mg"],"PO","sedative","C-IV")
add("Zaleplon",["sonata","zaleplon"],["5mg","10mg"],"PO","sedative","C-IV")
add("Suvorexant",["belsomra","suvorexant"],["5mg","10mg","15mg","20mg"],"PO","sedative","C-IV")
add("Lemborexant",["dayvigo","lemborexant"],["5mg","10mg"],"PO","sedative","C-IV")
add("Ramelteon",["rozerem","ramelteon"],["8mg"],"PO","sedative","Rx")
add("Flumazenil",["romazicon","flumazenil"],["0.1mg/ml"],"IV","benzo antagonist","Rx")

# Antipsychotics
add("Quetiapine",["seroquel","seroquel xr","quetiapine"],["25mg","50mg","100mg","200mg","300mg","400mg"],"PO","antipsychotic","Rx")
add("Risperidone",["risperdal","risperdal consta","risperidone"],["0.25mg","0.5mg","1mg","2mg","3mg","4mg"],"PO","antipsychotic","Rx")
add("Olanzapine",["zyprexa","zyprexa zydis","olanzapine"],["2.5mg","5mg","10mg","15mg","20mg"],"PO","antipsychotic","Rx")
add("Aripiprazole",["abilify","abilify maintena","aripiprazole"],["2mg","5mg","10mg","15mg","20mg","30mg"],"PO","antipsychotic","Rx")
add("Ziprasidone",["geodon","ziprasidone"],["20mg","40mg","60mg","80mg"],"PO","antipsychotic","Rx")
add("Paliperidone",["invega","invega sustenna","paliperidone"],["1.5mg","3mg","6mg","9mg"],"PO","antipsychotic","Rx")
add("Lurasidone",["latuda","lurasidone"],["20mg","40mg","60mg","80mg","120mg"],"PO","antipsychotic","Rx")
add("Brexpiprazole",["rexulti","brexpiprazole"],["0.25mg","0.5mg","1mg","2mg","3mg","4mg"],"PO","antipsychotic","Rx")
add("Cariprazine",["vraylar","cariprazine"],["1.5mg","3mg","4.5mg","6mg"],"PO","antipsychotic","Rx")
add("Clozapine",["clozaril","fazaclo","clozapine"],["25mg","50mg","100mg","200mg"],"PO","antipsychotic","Rx")
add("Haloperidol",["haldol","haloperidol"],["0.5mg","1mg","2mg","5mg","10mg","20mg"],"PO","antipsychotic","Rx")
add("Haloperidol Decanoate",["haldol decanoate"],["50mg/ml","100mg/ml"],"IM","antipsychotic","Rx")
add("Chlorpromazine",["thorazine","chlorpromazine"],["10mg","25mg","50mg","100mg","200mg"],"PO","antipsychotic","Rx")
add("Fluphenazine",["prolixin","fluphenazine"],["1mg","2.5mg","5mg","10mg"],"PO","antipsychotic","Rx")
add("Perphenazine",["trilafon","perphenazine"],["2mg","4mg","8mg","16mg"],"PO","antipsychotic","Rx")
add("Pimozide",["orap","pimozide"],["1mg","2mg"],"PO","antipsychotic","Rx")

# Mood Stabilizers
add("Lithium",["lithobid","eskalith","lithium"],["150mg","300mg","450mg","600mg"],"PO","mood stabilizer","Rx")
add("Valproic Acid",["depakene","depakote","depakote er","divalproex","valproic acid"],["125mg","250mg","500mg","250mg/5ml"],"PO","mood stabilizer","Rx")
add("Lamotrigine",["lamictal","lamictal xr","lamotrigine"],["25mg","100mg","150mg","200mg","250mg","300mg"],"PO","mood stabilizer","Rx")
add("Carbamazepine",["tegretol","tegretol xr","equetro","carbamazepine"],["100mg","200mg","300mg","400mg"],"PO","mood stabilizer","Rx")
add("Oxcarbazepine",["trileptal","oxtellar","oxcarbazepine"],["150mg","300mg","600mg"],"PO","anticonvulsant","Rx")

# ADHD
add("Methylphenidate",["ritalin","ritalin la","concerta","methylphenidate"],["5mg","10mg","18mg","20mg","27mg","36mg","54mg"],"PO","stimulant","C-II")
add("Amphetamine-Dextroamphetamine",["adderall","adderall xr"],["5mg","10mg","15mg","20mg","25mg","30mg"],"PO","stimulant","C-II")
add("Lisdexamfetamine",["vyvanse","lisdexamfetamine"],["10mg","20mg","30mg","40mg","50mg","60mg","70mg"],"PO","stimulant","C-II")
add("Dexmethylphenidate",["focalin","focalin xr"],["2.5mg","5mg","10mg","15mg","20mg"],"PO","stimulant","C-II")
add("Atomoxetine",["strattera","atomoxetine"],["10mg","18mg","25mg","40mg","60mg","80mg","100mg"],"PO","ADHD non-stimulant","Rx")
add("Guanfacine ER",["intuniv","guanfacine"],["1mg","2mg","3mg","4mg"],"PO","ADHD non-stimulant","Rx")
add("Clonidine ER",["kapvay"],["0.1mg","0.2mg"],"PO","ADHD non-stimulant","Rx")

# ═══════════════════════════════════════════
# ANTICONVULSANTS
# ═══════════════════════════════════════════
add("Levetiracetam",["keppra","keppra xr","levetiracetam"],["250mg","500mg","750mg","1000mg"],"PO","anticonvulsant","Rx")
add("Phenytoin",["dilantin","phenytek","phenytoin"],["30mg","100mg","200mg","300mg"],"PO","anticonvulsant","Rx")
add("Phenobarbital",["phenobarbital","luminal"],["15mg","30mg","60mg","100mg"],"PO","anticonvulsant","C-IV")
add("Topiramate",["topamax","trokendi","topiramate"],["25mg","50mg","100mg","200mg"],"PO","anticonvulsant","Rx")
add("Gabapentin",["neurontin","gralise","gabapentin"],["100mg","300mg","400mg","600mg","800mg"],"PO","anticonvulsant","Rx")
add("Pregabalin",["lyrica","lyrica cr","pregabalin"],["25mg","50mg","75mg","100mg","150mg","200mg","225mg","300mg"],"PO","anticonvulsant","C-V")
add("Zonisamide",["zonegran","zonisamide"],["25mg","50mg","100mg"],"PO","anticonvulsant","Rx")
add("Lacosamide",["vimpat","lacosamide"],["50mg","100mg","150mg","200mg"],"PO","anticonvulsant","C-V")
add("Brivaracetam",["briviact"],["10mg","25mg","50mg","75mg","100mg"],"PO","anticonvulsant","C-V")
add("Clobazam",["onfi","clobazam"],["5mg","10mg","20mg"],"PO","anticonvulsant","C-IV")
add("Ethosuximide",["zarontin","ethosuximide"],["250mg"],"PO","anticonvulsant","Rx")
add("Rufinamide",["banzel"],["200mg","400mg"],"PO","anticonvulsant","Rx")
add("Vigabatrin",["sabril","vigabatrin"],["500mg"],"PO","anticonvulsant","Rx")
add("Cannabidiol",["epidiolex"],["100mg/ml"],"PO","anticonvulsant","C-V")
add("Perampanel",["fycompa"],["2mg","4mg","6mg","8mg","10mg","12mg"],"PO","anticonvulsant","C-III")
add("Cenobamate",["xcopri"],["12.5mg","25mg","50mg","100mg","150mg","200mg"],"PO","anticonvulsant","C-V")

# ═══════════════════════════════════════════
# ANTI-PARKINSON & NEUROLOGICAL
# ═══════════════════════════════════════════
add("Levodopa-Carbidopa",["sinemet","sinemet cr","rytary","carbidopa-levodopa"],["10/100mg","25/100mg","25/250mg","50/200mg"],"PO","anti-parkinson","Rx")
add("Pramipexole",["mirapex","mirapex er","pramipexole"],["0.125mg","0.25mg","0.5mg","0.75mg","1mg","1.5mg"],"PO","anti-parkinson","Rx")
add("Ropinirole",["requip","requip xl","ropinirole"],["0.25mg","0.5mg","1mg","2mg","3mg","4mg","5mg"],"PO","anti-parkinson","Rx")
add("Entacapone",["comtan","entacapone"],["200mg"],"PO","anti-parkinson","Rx")
add("Rasagiline",["azilect","rasagiline"],["0.5mg","1mg"],"PO","anti-parkinson","Rx")
add("Amantadine",["symmetrel","gocovri","amantadine"],["100mg","68.5mg","137mg"],"PO","anti-parkinson","Rx")
add("Benztropine",["cogentin","benztropine"],["0.5mg","1mg","2mg"],"PO","anti-parkinson","Rx")
add("Trihexyphenidyl",["artane","trihexyphenidyl"],["2mg","5mg"],"PO","anti-parkinson","Rx")
add("Sumatriptan",["imitrex","sumatriptan"],["25mg","50mg","100mg","6mg/0.5ml"],"PO","triptan","Rx")
add("Rizatriptan",["maxalt","rizatriptan"],["5mg","10mg"],"PO","triptan","Rx")
add("Zolmitriptan",["zomig","zolmitriptan"],["2.5mg","5mg"],"PO","triptan","Rx")
add("Eletriptan",["relpax","eletriptan"],["20mg","40mg"],"PO","triptan","Rx")
add("Almotriptan",["axert","almotriptan"],["6.25mg","12.5mg"],"PO","triptan","Rx")
add("Frovatriptan",["frova","frovatriptan"],["2.5mg"],"PO","triptan","Rx")
add("Naratriptan",["amerge","naratriptan"],["1mg","2.5mg"],"PO","triptan","Rx")
add("Erenumab",["aimovig","erenumab"],["70mg","140mg"],"SC","CGRP inhibitor","Rx")
add("Fremanezumab",["ajovy","fremanezumab"],["225mg"],"SC","CGRP inhibitor","Rx")
add("Galcanezumab",["emgality","galcanezumab"],["120mg"],"SC","CGRP inhibitor","Rx")
add("Rimegepant",["nurtec","rimegepant"],["75mg"],"PO","CGRP inhibitor","Rx")
add("Ubrogepant",["ubrelvy","ubrogepant"],["50mg","100mg"],"PO","CGRP inhibitor","Rx")
add("Memantine",["namenda","namenda xr","memantine"],["5mg","10mg","14mg","21mg","28mg"],"PO","NMDA antagonist","Rx")
add("Donepezil",["aricept","donepezil"],["5mg","10mg","23mg"],"PO","cholinesterase inhibitor","Rx")
add("Rivastigmine",["exelon","exelon patch","rivastigmine"],["1.5mg","3mg","4.5mg","6mg","4.6mg/24hr","9.5mg/24hr","13.3mg/24hr"],"PO","cholinesterase inhibitor","Rx")
add("Galantamine",["razadyne","razadyne er","galantamine"],["4mg","8mg","12mg"],"PO","cholinesterase inhibitor","Rx")
add("Riluzole",["rilutek","riluzole"],["50mg"],"PO","neuroprotective","Rx")
add("Baclofen",["lioresal","gablofen","baclofen"],["5mg","10mg","20mg"],"PO","muscle relaxant","Rx")
add("Tizanidine",["zanaflex","tizanidine"],["2mg","4mg"],"PO","muscle relaxant","Rx")
add("Cyclobenzaprine",["flexeril","amrix","cyclobenzaprine"],["5mg","7.5mg","10mg","15mg","30mg"],"PO","muscle relaxant","Rx")
add("Methocarbamol",["robaxin","methocarbamol"],["500mg","750mg"],"PO","muscle relaxant","Rx")
add("Carisoprodol",["soma","carisoprodol"],["250mg","350mg"],"PO","muscle relaxant","C-IV")
add("Dantrolene",["dantrium","dantrolene"],["25mg","50mg","100mg"],"PO","muscle relaxant","Rx")
add("Orphenadrine",["norflex","orphenadrine"],["100mg"],"PO","muscle relaxant","Rx")

# ═══════════════════════════════════════════
# CORTICOSTEROIDS
# ═══════════════════════════════════════════
add("Prednisone",["deltasone","rayos","prednisone"],["1mg","2.5mg","5mg","10mg","20mg","50mg"],"PO","corticosteroid","Rx")
add("Prednisolone",["prelone","orapred","pediapred","prednisolone"],["5mg","15mg/5ml"],"PO","corticosteroid","Rx")
add("Methylprednisolone Oral",["medrol","methylprednisolone"],["4mg","8mg","16mg","32mg"],"PO","corticosteroid","Rx")
add("Methylprednisolone Injectable",["solu-medrol","depo-medrol"],["40mg","125mg","500mg","1g"],"IV","corticosteroid","Rx")
add("Dexamethasone",["decadron","dexamethasone"],["0.5mg","0.75mg","1mg","1.5mg","2mg","4mg","6mg"],"PO","corticosteroid","Rx")
add("Hydrocortisone Oral",["cortef","hydrocortisone"],["5mg","10mg","20mg"],"PO","corticosteroid","Rx")
add("Hydrocortisone Injectable",["solu-cortef"],["100mg","250mg","500mg"],"IV","corticosteroid","Rx")
add("Triamcinolone Injectable",["kenalog","triamcinolone"],["10mg/ml","40mg/ml"],"IM","corticosteroid","Rx")
add("Budesonide Oral",["entocort","uceris","budesonide"],["3mg","9mg"],"PO","corticosteroid","Rx")
add("Fludrocortisone",["florinef","fludrocortisone"],["0.1mg"],"PO","corticosteroid","Rx")

# ═══════════════════════════════════════════
# THYROID & ENDOCRINE
# ═══════════════════════════════════════════
add("Levothyroxine",["synthroid","levoxyl","tirosint","unithroid","levothyroxine"],["25mcg","50mcg","75mcg","88mcg","100mcg","112mcg","125mcg","137mcg","150mcg","175mcg","200mcg","300mcg"],"PO","thyroid","Rx")
add("Liothyronine",["cytomel","triostat","liothyronine"],["5mcg","25mcg","50mcg"],"PO","thyroid","Rx")
add("Methimazole",["tapazole","methimazole"],["5mg","10mg"],"PO","antithyroid","Rx")
add("Propylthiouracil",["ptu","propylthiouracil"],["50mg"],"PO","antithyroid","Rx")
add("Desmopressin",["ddavp","stimate","desmopressin"],["0.1mg","0.2mg","10mcg nasal"],"PO","hormone","Rx")
add("Cabergoline",["dostinex","cabergoline"],["0.5mg"],"PO","dopamine agonist","Rx")
add("Octreotide",["sandostatin","octreotide"],["50mcg/ml","100mcg/ml","200mcg/ml","500mcg/ml"],"SC","somatostatin analog","Rx")

# Reproductive/Hormonal
add("Estradiol Oral",["estrace","estradiol"],["0.5mg","1mg","2mg"],"PO","estrogen","Rx")
add("Estradiol Patch",["vivelle-dot","climara","estradiol patch"],["0.025mg/day","0.0375mg/day","0.05mg/day","0.075mg/day","0.1mg/day"],"TD","estrogen","Rx")
add("Conjugated Estrogens",["premarin","conjugated estrogens"],["0.3mg","0.625mg","0.9mg","1.25mg"],"PO","estrogen","Rx")
add("Medroxyprogesterone Oral",["provera","medroxyprogesterone"],["2.5mg","5mg","10mg"],"PO","progestin","Rx")
add("Medroxyprogesterone Injectable",["depo-provera","depo-subq provera"],["150mg/ml","104mg/0.65ml"],"IM","progestin","Rx")
add("Progesterone",["prometrium","crinone","progesterone"],["100mg","200mg"],"PO","progestin","Rx")
add("Testosterone Cypionate",["depo-testosterone","testosterone cypionate"],["100mg/ml","200mg/ml"],"IM","androgen","C-III")
add("Testosterone Gel",["androgel","testim","vogelxo"],["1%","1.62%"],"TOP","androgen","C-III")
add("Testosterone Patch",["androderm"],["2mg/day","4mg/day"],"TD","androgen","C-III")
add("Finasteride",["proscar","propecia","finasteride"],["1mg","5mg"],"PO","5-alpha reductase inhibitor","Rx")
add("Dutasteride",["avodart","dutasteride"],["0.5mg"],"PO","5-alpha reductase inhibitor","Rx")
add("Tamsulosin",["flomax","tamsulosin"],["0.4mg"],"PO","alpha blocker","Rx")
add("Sildenafil",["viagra","revatio","sildenafil"],["20mg","25mg","50mg","100mg"],"PO","PDE5 inhibitor","Rx")
add("Tadalafil",["cialis","adcirca","tadalafil"],["2.5mg","5mg","10mg","20mg"],"PO","PDE5 inhibitor","Rx")
add("Vardenafil",["levitra","staxyn","vardenafil"],["5mg","10mg","20mg"],"PO","PDE5 inhibitor","Rx")

# Contraceptives
add("Ethinyl Estradiol-Norgestimate",["ortho tri-cyclen","sprintec","tri-sprintec"],["35mcg/0.25mg"],"PO","contraceptive","Rx")
add("Ethinyl Estradiol-Levonorgestrel",["alesse","aviane","levlen","tri-levlen"],["20mcg/0.1mg","30mcg/0.15mg"],"PO","contraceptive","Rx")
add("Ethinyl Estradiol-Drospirenone",["yaz","yasmin","ocella","beyaz"],["20mcg/3mg","30mcg/3mg"],"PO","contraceptive","Rx")
add("Ethinyl Estradiol-Norethindrone",["loestrin","lo loestrin fe","junel","microgestin"],["20mcg/1mg","30mcg/1.5mg"],"PO","contraceptive","Rx")
add("Ethinyl Estradiol-Desogestrel",["apri","desogen","kariva"],["30mcg/0.15mg"],"PO","contraceptive","Rx")
add("Norethindrone",["nor-qd","camila","errin","micronor","norethindrone"],["0.35mg"],"PO","contraceptive","Rx")
add("Levonorgestrel IUD",["mirena","kyleena","liletta","skyla"],["52mg","19.5mg","13.5mg"],"IUD","contraceptive","Rx")
add("Etonogestrel Implant",["nexplanon","etonogestrel"],["68mg"],"SC","contraceptive","Rx")
add("Levonorgestrel Emergency",["plan b","plan b one-step","levonorgestrel"],["1.5mg"],"PO","emergency contraceptive","OTC")

# ═══════════════════════════════════════════
# DERMATOLOGICAL
# ═══════════════════════════════════════════
add("Hydrocortisone Topical",["cortisone-10","cortizone","hydrocortisone cream"],["0.5%","1%","2.5%"],"TOP","topical corticosteroid","OTC")
add("Triamcinolone Topical",["kenalog cream","triamcinolone cream"],["0.025%","0.1%","0.5%"],"TOP","topical corticosteroid","Rx")
add("Betamethasone Topical",["diprolene","luxiq","betamethasone cream"],["0.05%","0.1%"],"TOP","topical corticosteroid","Rx")
add("Clobetasol",["temovate","clobex","clobetasol"],["0.05%"],"TOP","topical corticosteroid","Rx")
add("Mometasone Topical",["elocon","mometasone cream"],["0.1%"],"TOP","topical corticosteroid","Rx")
add("Fluocinonide",["vanos","lidex","fluocinonide"],["0.05%","0.1%"],"TOP","topical corticosteroid","Rx")
add("Fluticasone Topical",["cutivate","fluticasone cream"],["0.005%","0.05%"],"TOP","topical corticosteroid","Rx")
add("Desonide",["desowen","desonide"],["0.05%"],"TOP","topical corticosteroid","Rx")
add("Mupirocin",["bactroban","centany","mupirocin"],["2%"],"TOP","topical antibiotic","Rx")
add("Bacitracin",["bacitracin"],["500U/g"],"TOP","topical antibiotic","OTC")
add("Neomycin-Polymyxin-Bacitracin",["neosporin","triple antibiotic"],["combo"],"TOP","topical antibiotic","OTC")
add("Silver Sulfadiazine",["silvadene","ssd","silver sulfadiazine"],["1%"],"TOP","topical antibiotic","Rx")
add("Permethrin",["elimite","nix","permethrin"],["1%","5%"],"TOP","scabicide","Rx")
add("Ivermectin Topical",["soolantra","sklice","ivermectin cream"],["0.5%","1%"],"TOP","antiparasitic","Rx")
add("Tretinoin",["retin-a","retin-a micro","tretinoin"],["0.025%","0.05%","0.1%"],"TOP","retinoid","Rx")
add("Adapalene",["differin","adapalene"],["0.1%","0.3%"],"TOP","retinoid","OTC")
add("Benzoyl Peroxide",["benzac","panoxyl","benzoyl peroxide"],["2.5%","5%","10%"],"TOP","acne treatment","OTC")
add("Clindamycin Topical",["cleocin t","clindagel","evoclin"],["1%"],"TOP","topical antibiotic","Rx")
add("Metronidazole Topical",["metrogel","metrocream","noritate"],["0.75%","1%"],"TOP","topical antibiotic","Rx")
add("Calcipotriene",["dovonex","sorilux","calcipotriene"],["0.005%"],"TOP","vitamin D analog","Rx")
add("Tacrolimus Topical",["protopic","tacrolimus ointment"],["0.03%","0.1%"],"TOP","topical immunomodulator","Rx")
add("Pimecrolimus",["elidel","pimecrolimus"],["1%"],"TOP","topical immunomodulator","Rx")

# ═══════════════════════════════════════════
# OPHTHALMIC
# ═══════════════════════════════════════════
add("Latanoprost",["xalatan","latanoprost"],["0.005%"],"OPTH","glaucoma","Rx")
add("Timolol Ophthalmic",["timoptic","betimol","timolol eye drops"],["0.25%","0.5%"],"OPTH","glaucoma","Rx")
add("Brimonidine Ophthalmic",["alphagan","alphagan p","brimonidine"],["0.1%","0.15%","0.2%"],"OPTH","glaucoma","Rx")
add("Dorzolamide",["trusopt","dorzolamide"],["2%"],"OPTH","glaucoma","Rx")
add("Dorzolamide-Timolol",["cosopt","dorzolamide-timolol"],["2%/0.5%"],"OPTH","glaucoma","Rx")
add("Bimatoprost",["lumigan","bimatoprost"],["0.01%","0.03%"],"OPTH","glaucoma","Rx")
add("Travoprost",["travatan z","travoprost"],["0.004%"],"OPTH","glaucoma","Rx")
add("Prednisolone Ophthalmic",["pred forte","omnipred","prednisolone eye drops"],["1%"],"OPTH","ophthalmic steroid","Rx")
add("Ciprofloxacin Ophthalmic",["ciloxan","ciprofloxacin eye drops"],["0.3%"],"OPTH","ophthalmic antibiotic","Rx")
add("Moxifloxacin Ophthalmic",["vigamox","moxeza"],["0.5%"],"OPTH","ophthalmic antibiotic","Rx")
add("Erythromycin Ophthalmic",["ilotycin","erythromycin eye ointment"],["0.5%"],"OPTH","ophthalmic antibiotic","Rx")
add("Tobramycin Ophthalmic",["tobrex","tobramycin eye drops"],["0.3%"],"OPTH","ophthalmic antibiotic","Rx")
add("Olopatadine",["patanol","pataday","pazeo","olopatadine"],["0.1%","0.2%","0.7%"],"OPTH","ophthalmic antihistamine","Rx")
add("Ketotifen Ophthalmic",["zaditor","alaway","ketotifen eye drops"],["0.025%"],"OPTH","ophthalmic antihistamine","OTC")
add("Artificial Tears",["refresh","systane","genteal","artificial tears"],["0.5%","1%"],"OPTH","eye lubricant","OTC")

# ═══════════════════════════════════════════
# ALLERGY & IMMUNOLOGY
# ═══════════════════════════════════════════
add("Cetirizine",["zyrtec","cetirizine"],["5mg","10mg","1mg/ml"],"PO","antihistamine","OTC")
add("Loratadine",["claritin","alavert","loratadine"],["10mg"],"PO","antihistamine","OTC")
add("Fexofenadine",["allegra","fexofenadine"],["60mg","180mg"],"PO","antihistamine","OTC")
add("Levocetirizine",["xyzal","levocetirizine"],["2.5mg","5mg"],"PO","antihistamine","OTC")
add("Diphenhydramine",["benadryl","diphenhydramine"],["25mg","50mg","12.5mg/5ml"],"PO","antihistamine","OTC")
add("Chlorpheniramine",["chlor-trimeton","chlorpheniramine"],["4mg"],"PO","antihistamine","OTC")
add("Fluticasone Nasal",["flonase","fluticasone nasal spray"],["50mcg/spray"],"NASAL","nasal corticosteroid","OTC")
add("Mometasone Nasal",["nasonex","mometasone nasal spray"],["50mcg/spray"],"NASAL","nasal corticosteroid","Rx")
add("Budesonide Nasal",["rhinocort","budesonide nasal spray"],["32mcg/spray"],"NASAL","nasal corticosteroid","OTC")
add("Triamcinolone Nasal",["nasacort","triamcinolone nasal spray"],["55mcg/spray"],"NASAL","nasal corticosteroid","OTC")
add("Azelastine Nasal",["astelin","astepro","azelastine nasal"],["137mcg/spray"],"NASAL","nasal antihistamine","Rx")
add("Epinephrine Auto-Injector",["epipen","epipen jr","auvi-q","epinephrine"],["0.15mg","0.3mg"],"IM","epinephrine","Rx")
add("Prednisone Burst Pack",["prednisone dose pack"],["5mg x 21","10mg x 21"],"PO","corticosteroid","Rx")
add("Cromolyn Sodium",["nasalcrom","gastrocrom","cromolyn"],["5.2mg/spray","100mg/5ml"],"NASAL","mast cell stabilizer","OTC")

# ═══════════════════════════════════════════
# OSTEOPOROSIS & BONE
# ═══════════════════════════════════════════
add("Alendronate",["fosamax","binosto","alendronate"],["5mg","10mg","35mg","70mg"],"PO","bisphosphonate","Rx")
add("Risedronate",["actonel","atelvia","risedronate"],["5mg","35mg","150mg"],"PO","bisphosphonate","Rx")
add("Ibandronate",["boniva","ibandronate"],["150mg","3mg/3ml"],"PO","bisphosphonate","Rx")
add("Zoledronic Acid",["reclast","zometa","zoledronic acid"],["4mg","5mg"],"IV","bisphosphonate","Rx")
add("Denosumab",["prolia","xgeva","denosumab"],["60mg","120mg"],"SC","bone agent","Rx")
add("Teriparatide",["forteo","teriparatide"],["20mcg"],"SC","bone agent","Rx")
add("Raloxifene",["evista","raloxifene"],["60mg"],"PO","SERM","Rx")
add("Calcitonin",["miacalcin","fortical","calcitonin"],["200IU/spray"],"NASAL","bone agent","Rx")

# ═══════════════════════════════════════════
# GOUT & RHEUMATOLOGY
# ═══════════════════════════════════════════
add("Allopurinol",["zyloprim","aloprim","allopurinol"],["100mg","300mg"],"PO","uric acid lowering","Rx")
add("Febuxostat",["uloric","febuxostat"],["40mg","80mg"],"PO","uric acid lowering","Rx")
add("Colchicine",["colcrys","mitigare","colchicine"],["0.6mg"],"PO","gout","Rx")
add("Probenecid",["probalan","probenecid"],["500mg"],"PO","uricosuric","Rx")
add("Methotrexate",["trexall","otrexup","rasuvo","methotrexate"],["2.5mg","5mg","7.5mg","10mg","15mg","25mg"],"PO","DMARD","Rx")
add("Hydroxychloroquine",["plaquenil","hydroxychloroquine"],["200mg"],"PO","DMARD","Rx")
add("Leflunomide",["arava","leflunomide"],["10mg","20mg"],"PO","DMARD","Rx")
add("Sulfasalazine Rheumatic",["azulfidine en","sulfasalazine rheumatic"],["500mg"],"PO","DMARD","Rx")
add("Adalimumab",["humira","adalimumab"],["20mg","40mg"],"SC","biologic DMARD","Rx")
add("Etanercept",["enbrel","etanercept"],["25mg","50mg"],"SC","biologic DMARD","Rx")
add("Infliximab",["remicade","inflectra","renflexis","infliximab"],["100mg"],"IV","biologic DMARD","Rx")
add("Tofacitinib",["xeljanz","xeljanz xr","tofacitinib"],["5mg","11mg"],"PO","JAK inhibitor","Rx")
add("Baricitinib",["olumiant","baricitinib"],["1mg","2mg"],"PO","JAK inhibitor","Rx")
add("Upadacitinib",["rinvoq","upadacitinib"],["15mg","30mg","45mg"],"PO","JAK inhibitor","Rx")
add("Apremilast",["otezla","apremilast"],["10mg","20mg","30mg"],"PO","PDE4 inhibitor","Rx")

# ═══════════════════════════════════════════
# SUPPLEMENTS & VITAMINS
# ═══════════════════════════════════════════
add("Vitamin D3",["cholecalciferol","d3","vitamin d"],["400IU","1000IU","2000IU","5000IU","50000IU"],"PO","vitamin","OTC")
add("Calcium Carbonate Supplement",["caltrate","os-cal","calcium"],["500mg","600mg"],"PO","mineral","OTC")
add("Calcium Citrate",["citracal","calcium citrate"],["200mg","315mg"],"PO","mineral","OTC")
add("Iron Sulfate",["feosol","fer-in-sol","ferrous sulfate","iron"],["325mg","65mg elemental"],"PO","mineral","OTC")
add("Folic Acid",["folvite","folic acid"],["0.4mg","0.8mg","1mg","5mg"],"PO","vitamin","OTC")
add("Vitamin B12",["cyanocobalamin","methylcobalamin","b12"],["100mcg","500mcg","1000mcg","2500mcg"],"PO","vitamin","OTC")
add("Vitamin B12 Injectable",["cyanocobalamin injection"],["1000mcg/ml"],"IM","vitamin","Rx")
add("Potassium Chloride",["klor-con","k-dur","micro-k","potassium chloride"],["8mEq","10mEq","20mEq"],"PO","electrolyte","Rx")
add("Magnesium Oxide",["mag-ox","magnesium oxide"],["200mg","400mg"],"PO","mineral","OTC")
add("Zinc Sulfate",["zinc","zinc sulfate","galzin"],["50mg","220mg"],"PO","mineral","OTC")
add("Thiamine",["vitamin b1","thiamine"],["50mg","100mg"],"PO","vitamin","OTC")
add("Pyridoxine",["vitamin b6","pyridoxine"],["25mg","50mg","100mg"],"PO","vitamin","OTC")
add("Multivitamin",["centrum","one-a-day","multivitamin"],["1 tab"],"PO","vitamin","OTC")
add("Prenatal Vitamin",["prenatal","prenatal vitamin"],["1 tab"],"PO","vitamin","Rx")

# ═══════════════════════════════════════════
# EMERGENCY & CRITICAL CARE
# ═══════════════════════════════════════════
add("Epinephrine",["adrenalin","epinephrine"],["1mg/ml","0.1mg/ml"],"IV","vasopressor","Rx")
add("Norepinephrine",["levophed","norepinephrine"],["1mg/ml","4mg/4ml"],"IV","vasopressor","Rx")
add("Dopamine",["intropin","dopamine"],["400mg/250ml","800mg/250ml"],"IV","vasopressor","Rx")
add("Dobutamine",["dobutrex","dobutamine"],["250mg/20ml"],"IV","inotrope","Rx")
add("Vasopressin",["vasostrict","vasopressin"],["20U/ml"],"IV","vasopressor","Rx")
add("Phenylephrine",["neo-synephrine","phenylephrine"],["10mg/ml"],"IV","vasopressor","Rx")
add("Atropine",["atropine sulfate"],["0.5mg/ml","1mg/ml"],"IV","anticholinergic","Rx")
add("Adenosine",["adenocard","adenosine"],["3mg/ml","6mg/2ml"],"IV","antiarrhythmic","Rx")
add("Amiodarone",["cordarone","pacerone","nexterone","amiodarone"],["100mg","200mg","400mg","150mg/3ml"],"PO","antiarrhythmic","Rx")
add("Lidocaine Injectable",["xylocaine","lidocaine"],["1%","2%","10mg/ml","20mg/ml"],"IV","antiarrhythmic","Rx")
add("Digoxin",["lanoxin","digitek","digoxin"],["0.0625mg","0.125mg","0.25mg"],"PO","cardiac glycoside","Rx")
add("Nitroglycerin SL",["nitrostat","nitroglycerin","nitro sl"],["0.3mg","0.4mg","0.6mg"],"SL","antianginal","Rx")
add("Nitroglycerin IV",["nitroglycerin iv"],["5mg/ml","25mg/250ml","50mg/250ml"],"IV","antianginal","Rx")
add("Nitroglycerin Patch",["nitro-dur","minitran","nitroglycerin patch"],["0.1mg/hr","0.2mg/hr","0.4mg/hr","0.6mg/hr"],"TD","antianginal","Rx")
add("Isosorbide Mononitrate",["imdur","monoket","isosorbide mononitrate"],["10mg","20mg","30mg","60mg","120mg"],"PO","antianginal","Rx")
add("Isosorbide Dinitrate",["isordil","dilatrate","isosorbide dinitrate"],["5mg","10mg","20mg","40mg"],"PO","antianginal","Rx")
add("Alteplase",["activase","tpa","alteplase"],["50mg","100mg"],"IV","thrombolytic","Rx")
add("Tenecteplase",["tnkase","tenecteplase"],["50mg"],"IV","thrombolytic","Rx")
add("Protamine",["protamine sulfate"],["10mg/ml"],"IV","heparin reversal","Rx")
add("Idarucizumab",["praxbind"],["2.5g/50ml"],"IV","dabigatran reversal","Rx")
add("Andexanet Alfa",["andexxa"],["200mg"],"IV","factor Xa reversal","Rx")
add("Sodium Bicarbonate",["sodium bicarbonate"],["4.2%","7.5%","8.4%","50mEq/50ml"],"IV","alkalinizer","Rx")
add("Calcium Gluconate Injectable",["calcium gluconate"],["100mg/ml","1g/10ml"],"IV","electrolyte","Rx")
add("Activated Charcoal",["actidose","charcoal","activated charcoal"],["25g","50g"],"PO","antidote","OTC")
add("N-Acetylcysteine",["acetadote","mucomyst","nac"],["200mg/ml","600mg"],"IV","antidote","Rx")

# ═══════════════════════════════════════════
# ANESTHETICS & SEDATION
# ═══════════════════════════════════════════
add("Propofol",["diprivan","propofol"],["10mg/ml"],"IV","anesthetic","Rx")
add("Ketamine",["ketalar","ketamine"],["10mg/ml","50mg/ml","100mg/ml"],"IV","anesthetic","C-III")
add("Etomidate",["amidate","etomidate"],["2mg/ml"],"IV","anesthetic","Rx")
add("Lidocaine Local",["xylocaine","lidocaine local"],["1%","2%"],"INJ","local anesthetic","Rx")
add("Lidocaine-Epinephrine",["xylocaine with epi"],["1%/1:100000","2%/1:100000"],"INJ","local anesthetic","Rx")
add("Bupivacaine",["marcaine","sensorcaine","bupivacaine"],["0.25%","0.5%"],"INJ","local anesthetic","Rx")
add("Ropivacaine",["naropin","ropivacaine"],["0.2%","0.5%","0.75%"],"INJ","local anesthetic","Rx")
add("Lidocaine Topical",["lidoderm","xylocaine jelly","lidocaine patch"],["4%","5%"],"TOP","local anesthetic","Rx")
add("Lidocaine-Prilocaine",["emla","emla cream"],["2.5%/2.5%"],"TOP","local anesthetic","Rx")
add("Succinylcholine",["anectine","quelicin","succinylcholine"],["20mg/ml"],"IV","neuromuscular blocker","Rx")
add("Rocuronium",["zemuron","rocuronium"],["10mg/ml"],"IV","neuromuscular blocker","Rx")
add("Cisatracurium",["nimbex","cisatracurium"],["2mg/ml","10mg/ml"],"IV","neuromuscular blocker","Rx")
add("Sugammadex",["bridion","sugammadex"],["100mg/ml"],"IV","reversal agent","Rx")
add("Neostigmine",["prostigmin","bloxiverz","neostigmine"],["0.5mg/ml","1mg/ml"],"IV","reversal agent","Rx")
add("Dexmedetomidine",["precedex","dexmedetomidine"],["4mcg/ml","100mcg/ml"],"IV","sedative","Rx")

# ═══════════════════════════════════════════
# MISCELLANEOUS
# ═══════════════════════════════════════════
add("Ivermectin Oral",["stromectol","ivermectin"],["3mg"],"PO","antiparasitic","Rx")
add("Albendazole",["albenza","albendazole"],["200mg"],"PO","antiparasitic","Rx")
add("Mebendazole",["emverm","vermox","mebendazole"],["100mg"],"PO","antiparasitic","Rx")
add("Praziquantel",["biltricide","praziquantel"],["600mg"],"PO","antiparasitic","Rx")
add("Methotrexate Injection",["otrexup","rasuvo","methotrexate inj"],["7.5mg","10mg","15mg","20mg","25mg"],"SC","immunosuppressant","Rx")
add("Azathioprine",["imuran","azasan","azathioprine"],["50mg","75mg","100mg"],"PO","immunosuppressant","Rx")
add("Mycophenolate",["cellcept","myfortic","mycophenolate"],["250mg","500mg"],"PO","immunosuppressant","Rx")
add("Cyclosporine",["neoral","sandimmune","gengraf","cyclosporine"],["25mg","50mg","100mg"],"PO","immunosuppressant","Rx")
add("Tacrolimus Oral",["prograf","envarsus","tacrolimus"],["0.5mg","1mg","5mg"],"PO","immunosuppressant","Rx")
add("Sirolimus",["rapamune","sirolimus"],["0.5mg","1mg","2mg"],"PO","immunosuppressant","Rx")
add("Filgrastim",["neupogen","zarxio","filgrastim"],["300mcg","480mcg"],"SC","colony stimulating factor","Rx")
add("Pegfilgrastim",["neulasta","pegfilgrastim"],["6mg"],"SC","colony stimulating factor","Rx")
add("Erythropoietin",["epogen","procrit","epo","epoetin alfa"],["2000U","3000U","4000U","10000U","40000U"],"SC","erythropoietin","Rx")
add("Darbepoetin",["aranesp","darbepoetin"],["25mcg","40mcg","60mcg","100mcg","200mcg"],"SC","erythropoietin","Rx")
add("Tranexamic Acid",["lysteda","cyklokapron","tranexamic acid"],["650mg","1g"],"PO","antifibrinolytic","Rx")
add("Aminocaproic Acid",["amicar","aminocaproic acid"],["500mg","1g"],"PO","antifibrinolytic","Rx")
add("Desmopressin Injectable",["ddavp injection"],["4mcg/ml"],"IV","hemostatic","Rx")
add("Phytonadione",["vitamin k","mephyton","phytonadione"],["1mg/0.5ml","5mg","10mg"],"PO","vitamin K","Rx")
add("Diphenhydramine Injectable",["benadryl injection"],["50mg/ml"],"IV","antihistamine","Rx")

# ═══════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════
formulary = {
    "source": "Based on FDA Orange Book, USP Drug Classification, and DEA Controlled Substances Schedules",
    "version": "1.0",
    "country": "US",
    "lastUpdated": "2025-01",
    "drugs": drugs
}

out = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "assets", "formulary", "us_formulary.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(formulary, f, indent=2, ensure_ascii=False)

cats = set(d["category"] for d in drugs)
scheds = {}
for d in drugs:
    s = d["scheduleClass"]
    scheds[s] = scheds.get(s, 0) + 1
codes = [d["code"] for d in drugs]
dupes = len(codes) - len(set(codes))

print(f"Generated {len(drugs)} drugs")
print(f"Categories: {len(cats)}")
print(f"Schedules: {dict(sorted(scheds.items()))}")
print(f"Duplicate codes: {dupes}")
print(f"Written to: {out}")
