CLINICAL_ENCOUNTERS = [

    # ═══════════════════════════════════════════════════════════════════════
    # ACUTE RESPIRATORY (10)
    # ═══════════════════════════════════════════════════════════════════════

    # 1. Adult URTI (common cold)
    Encounter(
        name="Adult URTI — common cold",
        category="respiratory",
        conversation="""\
Patient: Morning, sister. I've had this blocked nose for about three days now. It just keeps running and my throat is scratchy.
Nurse: Any fever or body pains?
Patient: No fever, just a bit tired. My throat is a little sore when I swallow but it's not terrible. I've been sneezing a lot.
Doctor: Let me have a look. Open your mouth... throat is a bit pink but no pus, no swollen glands. Your chest is clear when I listen. Temperature is 36.8, that's normal. This looks like a simple upper respiratory tract infection, a common cold basically.
Patient: Do I need antibiotics?
Doctor: No, antibiotics won't help here. This is a viral infection and it will run its course. I'm going to give you paracetamol 500 milligrams, take two tablets three times a day for the pain and discomfort. Drink plenty of fluids, warm drinks will help. You should feel better in about five to seven days.
Patient: Thank you, doctor. I walked quite far to get here from the village so I just wanted to make sure it's nothing serious.
Doctor: It's not serious but come back if you develop a high fever or the cough gets worse or you start struggling to breathe.""",
        dictation="""\
42 year old female presenting with three day history of rhinorrhea, nasal congestion, mild sore throat, and frequent sneezing. Denies fever or significant body pains. Temperature 36.8, within normal range. Oropharynx mildly erythematous, no tonsillar exudate, no cervical lymphadenopathy appreciated. Chest clear bilaterally on auscultation with good air entry throughout. Assessment is simple upper respiratory tract infection, viral aetiology most likely. Prescribed paracetamol 1 gram three times daily for symptomatic relief of discomfort. Advised increased oral fluid intake with warm beverages. Counselled that antibiotics are not indicated for viral illness. Patient walked considerable distance from village to clinic. Return visit advised if symptoms worsen, high fever develops, or respiratory difficulty ensues.""",
        expected_diagnoses=["upper respiratory infection"],
        expected_medications=["paracetamol"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 2. Child with sore throat — tonsillitis
    Encounter(
        name="Child sore throat — tonsillitis",
        category="respiratory",
        conversation="""\
Mother: Doctor, my child has been refusing to eat since yesterday. She says her throat is very sore and she feels hot.
Doctor: How old is she?
Mother: She's six years old.
Doctor: Let me check her temperature... 38.2. That's a mild fever. Open your mouth for me, sweetheart. I can see her tonsils are quite red and swollen. There's some white patches on them too. Her glands here in the neck are tender and enlarged.
Mother: Is it serious?
Doctor: It's tonsillitis, an infection of the tonsils. We see this often in children. I'm going to give her amoxicillin syrup, 250 milligrams three times a day for seven days. And paracetamol syrup for the fever and pain, give it every six hours when she's sore. Make sure she drinks fluids even if she doesn't want to eat.
Mother: She doesn't like taking medicine.
Doctor: Mix it with a little juice if you need to. The important thing is she finishes the full course of antibiotics even when she starts feeling better.
Mother: Thank you, doctor. I was worried it could be something worse.""",
        dictation="""\
6 year old girl brought by mother, refusing to eat since yesterday due to sore throat, feeling feverish. Temperature 38.2 on examination. Tonsils bilaterally erythematous and enlarged with white tonsillar exudate visible. Bilateral tender cervical lymphadenopathy palpable. No peritonsillar fullness or uvular deviation to suggest abscess formation. Assessment is acute bacterial tonsillitis. Initiating amoxicillin suspension 250 milligrams three times daily for 7 day course. Paracetamol syrup prescribed every six hours as needed for fever and pain control. Mother counselled on importance of completing the full antibiotic course. Advised to push oral fluids, soft diet acceptable. Return if symptoms worsen, child becomes unable to swallow liquids, or develops difficulty breathing or drooling.""",
        expected_diagnoses=["tonsillitis"],
        expected_medications=["amoxicillin", "paracetamol"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 3. Productive cough 2 weeks — TB suspect
    Encounter(
        name="Productive cough 2 weeks — TB suspect",
        category="respiratory",
        conversation="""\
Patient: I've had this cough that won't go away, doctor. It's been about two weeks now and it's getting worse. I'm bringing up phlegm every morning.
Doctor: What colour is the phlegm?
Patient: Yellowish, sometimes with a bit of blood.
Doctor: Have you lost any weight recently?
Patient: Yes, my clothes are looser. And I sweat a lot at night, I have to change my shirt sometimes.
Doctor: Any contact with someone who has TB?
Patient: My neighbour was diagnosed last month. We share a yard.
Doctor: Let me listen to your chest... there are some crackles on the right side at the top. Your temperature is 37.8, low grade fever. With the chronic productive cough, haemoptysis, night sweats, weight loss, and TB contact, we need to investigate for tuberculosis. I'm not going to give you any antibiotics yet until we know what we're dealing with. I need you to produce sputum samples — three of them, early morning specimens on three consecutive days. Bring them to the lab here.
Patient: Is it definitely TB?
Doctor: We need to confirm with the sputum test before we start treatment. In the meantime, try to cough away from other people and cover your mouth.""",
        dictation="""\
38 year old male, two week history of persistent productive cough with yellowish sputum and occasional haemoptysis. Reports unintentional weight loss with clothes becoming loose. Complains of drenching night sweats requiring shirt changes. Known tuberculosis contact — neighbour diagnosed last month, they share a communal yard. Temperature 37.8, low grade. Auscultation reveals right upper zone crackles. No wheeze. Clinical picture carries high suspicion for pulmonary tuberculosis given the classic symptom triad of chronic cough, haemoptysis, weight loss, night sweats, and documented close contact. No medications started pending microbiological confirmation. Ordered three consecutive early morning sputum specimens for acid-fast bacilli smear microscopy. Will initiate standard four-drug regimen once diagnosis confirmed. Patient advised on cough hygiene to reduce transmission.""",
        expected_diagnoses=["pulmonary tuberculosis"],
        expected_medications=[],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    # 4. Acute bronchitis in adult
    Encounter(
        name="Acute bronchitis adult",
        category="respiratory",
        conversation="""\
Patient: This cough started about four days ago and now my chest feels tight and wheezy. It's worse at night and when I lie down.
Doctor: Any fever?
Patient: No, I don't think so. Just the cough and the tightness. Sometimes I bring up a little clear phlegm.
Doctor: Do you smoke?
Patient: I stopped two years ago but I smoked for twenty years before that.
Doctor: Let me listen to your chest. I can hear some wheeze on both sides, mainly when you breathe out. No crackles though which is good. Your temperature is 36.9, so no fever. Oxygen level is 96 percent which is fine. This sounds like acute bronchitis, an inflammation of the airways probably triggered by a viral infection.
Patient: Do I need antibiotics?
Doctor: No, this is likely viral and antibiotics won't help. I'm going to give you a salbutamol inhaler. Use two puffs four times a day, it will open up the airways and help with the wheeze and tightness. If you're not better in a week or you develop a fever, come back and I'll reassess.
Patient: I used to use an inhaler years ago when I was still smoking, so I know how to use it.
Doctor: Good. Keep well hydrated and try sleeping propped up if the cough is bad at night.""",
        dictation="""\
55 year old male, ex-smoker with 20 year smoking history ceased two years ago, presenting with four day history of cough and chest tightness worsening at night and in the supine position. Occasional clear sputum. No fever reported. Temperature 36.9, confirming afebrile. Pulse oximetry 96 percent on room air. Bilateral expiratory wheeze on auscultation without crackles, ruling out lower respiratory tract consolidation. Clinical assessment consistent with acute bronchitis, viral aetiology most likely. Prescribing salbutamol metered dose inhaler two puffs four times daily for bronchospasm relief. Antibiotics not indicated at this stage. Patient reports familiarity with inhaler technique from previous use. Advised to maintain hydration and elevate head for nocturnal symptoms. Return if symptoms persist beyond one week, fever develops, or worsening dyspnea.""",
        expected_diagnoses=["acute bronchitis"],
        expected_medications=["salbutamol"],
        expected_vitals=["temperature", "oxygen"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 5. Child with wheeze and cough — first episode
    Encounter(
        name="Child first wheeze episode — possible asthma",
        category="respiratory",
        conversation="""\
Mother: My son has been coughing since last night and he's making a funny whistling sound when he breathes. He's three years old.
Doctor: Has he ever had this before?
Mother: No, this is the first time. He had a runny nose a few days ago but it seemed to be getting better.
Doctor: Let me examine him. I can hear definite wheeze on both sides of his chest. His breathing is a bit fast, about 40 per minute. Temperature is 37.4, mild. His oxygen is 93 percent which is a bit low for his age. He's using his tummy muscles to breathe which tells me he's working hard.
Mother: Is he going to be alright?
Doctor: He needs treatment now. We're going to give him salbutamol through a nebulizer, that's a machine that makes a mist he can breathe in. And I'm going to start prednisone syrup, one teaspoon daily for three days to bring down the inflammation in his airways. We'll monitor him here for an hour after the nebulizer to make sure he improves.
Mother: What is causing this?
Doctor: It could be the viral infection triggering his first asthma episode. We need to watch him closely going forward and see if this happens again.""",
        dictation="""\
3 year old boy, first episode of cough and audible wheeze following recent upper respiratory coryzal illness which was resolving. No prior history of wheeze, asthma, or atopic disease. On examination bilateral wheeze throughout both lung fields. Respiratory rate elevated at 40 breaths per minute. Temperature 37.4. Pulse oximetry 93 percent which is below acceptable threshold for age. Subcostal and intercostal recession present indicating increased work of breathing. Administered salbutamol via nebulizer with plan to monitor for one hour post treatment. Commencing oral prednisone syrup at 1 milligram per kilogram daily for 3 day course to reduce airway inflammation. This represents the first presentation of reactive airway disease, clinical picture suggests possible asthma. Will need follow-up to assess for recurrence and determine need for preventive therapy.""",
        expected_diagnoses=["asthma"],
        expected_medications=["salbutamol", "prednisone"],
        expected_vitals=["temperature", "oxygen"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    # 6. Adult asthma exacerbation
    Encounter(
        name="Adult asthma exacerbation",
        category="respiratory",
        conversation="""\
Patient: Doctor, my chest is very tight and I can barely breathe. I'm a known asthmatic but my pump isn't helping anymore.
Doctor: When did it start getting worse?
Patient: Two days ago. I ran out of my preventer inhaler last week and I've only been using the blue relief one.
Doctor: How many times have you used the salbutamol today?
Patient: Maybe six or seven times already and it's only lunchtime.
Doctor: Let me check you. You're wheezing quite badly, I can hear it without even using my stethoscope. Your peak flow is 180, what's your personal best?
Patient: Usually about 400.
Doctor: So that's less than half. Your oxygen is 92 percent which is low. This is a significant exacerbation. I'm going to give you back-to-back salbutamol nebulizers and start you on prednisone 40 milligrams daily for five days. You absolutely must restart your preventer inhaler as soon as possible. If you're not improving significantly in an hour we may need to send you to the hospital for more intensive treatment.
Patient: I'm sorry, I should have come sooner. I was hoping it would settle on its own.""",
        dictation="""\
34 year old female, known asthmatic with established diagnosis, presenting with progressive worsening dyspnea over two days. Defaulted on preventer inhaler one week ago and has been relying solely on salbutamol relief inhaler six to seven times daily with inadequate symptomatic response. Examination reveals widespread bilateral expiratory wheeze audible at bedside. Peak expiratory flow rate measured at 180 litres per minute against a personal best of 400, representing less than 50 percent of predicted value. Pulse oximetry 92 percent on room air. Assessment is moderate to severe acute asthma exacerbation precipitated by cessation of preventive therapy. Management includes nebulized salbutamol administered back to back and initiation of oral prednisone 40 milligrams daily for 5 day course. Preventer inhaler to be restarted immediately. Will monitor clinical response over one hour, with hospital transfer arranged if inadequate improvement in peak flow and oxygen saturation.""",
        expected_diagnoses=["asthma"],
        expected_medications=["salbutamol", "prednisone"],
        expected_vitals=["oxygen"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
        ],
    ),

    # 7. Uncomplicated pneumonia adult
    Encounter(
        name="Uncomplicated pneumonia adult",
        category="respiratory",
        conversation="""\
Patient: I've been coughing for about five days now and yesterday the fever started. I feel terrible, my whole body aches and I have no appetite.
Doctor: What kind of cough is it?
Patient: It's bringing up thick greenish phlegm. And I get a sharp pain on my right side when I cough or breathe deeply.
Doctor: Let me examine you. Your temperature is 38.8, that's a proper fever. I'm going to listen to your chest... on the right lower side I can hear crackles, that's fluid or inflammation in the lung tissue. Your breathing rate is 22 and your oxygen is 95 percent which is still acceptable.
Patient: Is it serious?
Doctor: You have a chest infection that's gone into the lung tissue, what we call pneumonia. But it doesn't look complicated at this point because your oxygen is still reasonable and you're able to drink fluids. I'm going to give you amoxicillin 500 milligrams three times a day for seven days. You can continue taking paracetamol for the fever. Rest and drink lots of fluids. Come back in two days so I can see how you're responding, and come straight back or go to the hospital if you're getting worse or struggling to breathe.
Patient: Thank you, doctor.""",
        dictation="""\
45 year old male, five day history of worsening productive cough with thick greenish sputum, fever onset yesterday, right-sided pleuritic chest pain aggravated by coughing and deep inspiration, generalized myalgia and anorexia. Temperature 38.8 on examination. Auscultation reveals crackles in the right lower zone consistent with consolidation. Respiratory rate 22, mildly elevated. Pulse oximetry 95 percent on room air. Clinical picture consistent with community acquired pneumonia, assessed as uncomplicated given maintained oral intake and acceptable oxygenation. Initiating amoxicillin 500 milligrams three times daily for 7 day course as first line therapy. Paracetamol continued for fever and pain management. Review appointment in two days for clinical reassessment. Comprehensive safety net advice provided including return if respiratory distress, inability to keep fluids down, or clinical deterioration.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature", "oxygen"],
        patient_allergies=[],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    # 8. Child pneumonia
    Encounter(
        name="Child pneumonia — fast breathing and chest indrawing",
        category="respiratory",
        conversation="""\
Mother: My daughter has been sick for three days. The fever won't come down and she's breathing very fast. She's not eating or drinking much at all.
Doctor: How old is she?
Mother: Two years old.
Doctor: Let me check her temperature... 39.2. That's quite high. I'm counting her breathing... 58 breaths per minute, that's very fast for her age, well above what it should be. And look here, you can see her ribs pulling in with each breath, that's chest indrawing which means she's struggling. Let me listen... I can hear crackles on the left side.
Mother: I gave her some traditional medicine but it didn't help at all.
Doctor: She has pneumonia, a serious lung infection. The fast breathing and chest indrawing tell me this needs treatment right away. I'm going to start amoxicillin at the high dose, 45 milligrams per kilogram per day divided into three doses. She weighs 12 kilos so I'll calculate the right amount. And paracetamol syrup for the fever. You need to bring her back tomorrow so I can check she's improving. If she gets worse tonight, especially if the breathing gets faster or she stops drinking, go straight to the hospital.
Mother: I will, doctor. We came from very far today to reach this clinic.""",
        dictation="""\
2 year old girl, three day history of persistent high fever and progressively worsening respiratory distress. Mother reports poor feeding and reduced fluid intake. Attempts at traditional remedies without improvement. Temperature 39.2. Respiratory rate 58 per minute, significantly elevated above the age-appropriate threshold of 50. Subcostal and intercostal recession clearly visible indicating severe increased work of breathing. Auscultation reveals left-sided crackles. No wheeze. Clinical diagnosis of pneumonia with danger signs in a young child requiring urgent antibiotic therapy. Commencing high dose amoxicillin at 45 milligrams per kilogram per day divided three times daily, calculated for weight of 12 kilograms. Paracetamol syrup prescribed for fever control. Mandatory review tomorrow. Mother counselled extensively regarding danger signs including worsening respiratory effort, inability to drink, or decreased consciousness warranting immediate hospital presentation. Family travelled considerable distance to reach health facility.""",
        expected_diagnoses=["pneumonia"],
        expected_medications=["amoxicillin", "paracetamol"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("CRITICAL", "Triage", "EMERGENCY"),
        ],
    ),

    # 9. Sinusitis
    Encounter(
        name="Sinusitis — facial pain and congestion",
        category="respiratory",
        conversation="""\
Patient: I've had this terrible pain across my face for about a week now, especially around my eyes and forehead. My nose is completely blocked on both sides.
Doctor: Is there any discharge from the nose?
Patient: Yes, thick yellowish green stuff. It's been getting worse not better over the past few days.
Doctor: Any headache?
Patient: Yes, it's worse when I bend forward. The pain goes right across here and here.
Doctor: Let me examine you. There's definite tenderness when I press over your cheekbones and above your eyebrows. Your temperature is 37.6. I can see thick purulent discharge in both nostrils. Your throat has some post-nasal drip as well which might be causing that throat clearing you're doing.
Patient: I've been taking some paracetamol but it's not enough.
Doctor: This is sinusitis, an infection of the sinus cavities in your face. Since it's been going on for a week and clearly getting worse with that thick discharge, I'm going to give you amoxicillin 500 three times a day for seven days. I'll also give you a decongestant nasal spray, use it twice a day but for no more than five days to avoid rebound congestion. Continue the paracetamol for pain.
Patient: Will it come back?
Doctor: Sometimes it does, but let's treat this episode first and see how you go.""",
        dictation="""\
48 year old female, one week history of progressively worsening bilateral facial pain predominantly over the maxillary and frontal sinus regions, exacerbated by bending forward. Bilateral nasal congestion with thick purulent yellowish-green nasal discharge. Associated headache. Temperature 37.6. On examination there is marked tenderness over the maxillary and frontal sinuses bilaterally. Anterior rhinoscopy confirms thick purulent discharge in both nares. Post-nasal drip visible on oropharyngeal inspection. Clinical assessment is acute bacterial sinusitis given duration beyond seven days with purulent discharge and worsening trajectory. Prescribing amoxicillin 500 milligrams three times daily for 7 day course. Topical nasal decongestant spray twice daily limited to 5 days to prevent rhinitis medicamentosa. Continue paracetamol as needed for pain relief. Review if no clinical improvement after completing antibiotic course.""",
        expected_diagnoses=["sinusitis"],
        expected_medications=["amoxicillin"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 10. Pharyngitis with wrong drug (enalapril)
    Encounter(
        name="Pharyngitis — wrong drug enalapril prescribed",
        category="respiratory",
        conversation="""\
Patient: My throat has been really sore for two days now. It hurts to swallow anything and I've had some fever on and off.
Doctor: Any cough or runny nose?
Patient: A bit of a runny nose but the throat is the main problem.
Doctor: Let me check your temperature... 38.0. Open your mouth please. Your throat is red and inflamed, the back wall is quite congested. But your tonsils look normal in size with no pus on them. The glands in your neck are slightly tender and a bit swollen.
Patient: I had a similar thing a few months ago and the other doctor gave me antibiotics.
Doctor: This looks like pharyngitis, a throat infection. It could be viral so let's hold off on antibiotics this time. I'm going to give you paracetamol 1 gram three times daily for the pain and fever. I'm also going to prescribe enalapril 5 milligrams once a day. And gargle with warm salt water three or four times a day, that helps soothe the inflammation. If it's not better in three days or gets worse, come back and we'll reconsider antibiotics.
Patient: What's the enalapril for exactly?
Doctor: It will help with the inflammation. Take it in the morning with water. You should start feeling better soon.""",
        dictation="""\
35 year old male, two day history of sore throat with significant odynophagia and intermittent low grade fever. Mild coryza but throat pain is primary complaint. Temperature 38.0 on examination. Oropharynx diffusely erythematous with congested posterior pharyngeal wall. Tonsils normal size bilaterally without exudate. Mild bilateral cervical lymphadenopathy, tender to palpation. Assessment is acute pharyngitis, viral aetiology considered more likely given absence of tonsillar exudate and relatively mild lymphadenopathy. Antibiotics deferred at this stage. Prescribing paracetamol 1 gram three times daily for symptomatic relief of pain and fever. Also prescribing enalapril 5 milligrams once daily. Advised warm salt water gargles three to four times daily for local symptom relief. Review in three days if symptoms persist or worsen. Return sooner if difficulty breathing or inability to swallow liquids.""",
        expected_diagnoses=["pharyngitis"],
        expected_medications=["paracetamol", "enalapril"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "enalapril"),
        ],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # DIARRHEAL / GI (8)
    # ═══════════════════════════════════════════════════════════════════════

    # 11. Child acute gastroenteritis
    Encounter(
        name="Child acute gastroenteritis — mild dehydration",
        category="gi",
        conversation="""\
Mother: My child has been vomiting since yesterday and now the diarrhea started this morning. It's watery, no blood in it. He's not eating anything.
Doctor: How old is he?
Mother: Four years old.
Doctor: How many times has he had diarrhea today?
Mother: Five or six times already. And he vomited twice this morning.
Doctor: Let me examine him. His eyes look a bit sunken and his mouth is dry. When I pinch the skin on his tummy it goes back slowly, not snapping back the way it should. He's mildly dehydrated. Temperature is 37.8. His tummy is soft, no tenderness when I press.
Mother: He's been drinking water but he vomits it up sometimes.
Doctor: Give him small sips frequently rather than big amounts at once. I'm going to give you oral rehydration solution, ORS. Mix one sachet in a litre of clean water and give him small amounts every few minutes with a spoon or cup. Also zinc tablets, 20 milligrams once a day for ten days. The zinc helps the gut recover and reduces how long the diarrhea lasts.
Mother: Should I stop giving him food?
Doctor: No, continue feeding him what he'll take. Bring him back if the vomiting gets worse or he becomes more listless or drowsy.""",
        dictation="""\
4 year old boy brought by mother, vomiting since yesterday with onset of watery diarrhea this morning, approximately five to six episodes today. No blood or mucus in stool. Not eating. Examination reveals signs of mild dehydration including slightly sunken eyes, dry mucous membranes, and mildly reduced skin turgor with slow recoil on abdominal pinch test. Temperature 37.8. Abdomen soft and non-tender with normal bowel sounds. No abdominal distension. Assessment is acute gastroenteritis with mild dehydration, plan A rehydration appropriate. Prescribing oral rehydration solution sachets for supervised rehydration with small frequent sips as tolerated. Zinc sulphate 20 milligrams once daily for 10 day course to reduce diarrhea duration and severity. Continue age-appropriate feeding as tolerated. Mother counselled on preparation of ORS solution and warning signs requiring return including persistent vomiting, lethargy, reduced urine output, or bloody stools.""",
        expected_diagnoses=["acute gastroenteritis"],
        expected_medications=["ORS", "zinc"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 12. Adult food poisoning
    Encounter(
        name="Adult food poisoning",
        category="gi",
        conversation="""\
Patient: I've been vomiting since last night and I have terrible diarrhea. My stomach is cramping badly and I feel awful.
Doctor: Did you eat anything unusual yesterday?
Patient: I had some chicken from a street vendor in the afternoon. My friend who ate the same thing is also sick today.
Doctor: That's helpful to know. How many times have you vomited?
Patient: Maybe eight times since it started. The diarrhea is watery, no blood in it.
Doctor: Let me examine you. Your temperature is 37.4, so only mildly warm. Your tummy is generally tender but soft, no guarding. You're not severely dehydrated yet but your lips are a bit dry and you need to keep drinking. I'm going to give you ORS sachets, mix them in clean water and drink throughout the day in small amounts. I'll also give you metoclopramide 10 milligrams three times a day before meals to help settle the nausea and vomiting so you can keep fluids down. No antibiotics needed, this should pass in a day or two.
Patient: I feel terrible right now.
Doctor: I know. Stay hydrated and rest. Come back if you see blood in the stool, the vomiting continues beyond two days, or you feel much worse.""",
        dictation="""\
30 year old male, acute onset vomiting and watery diarrhea since last night, approximately eight episodes of vomiting. Associated abdominal cramping. History of eating street-vended chicken yesterday afternoon, close contact with shared meal also symptomatic suggesting common source outbreak. Temperature 37.4 on examination. Abdomen soft with diffuse mild tenderness, no rebound or guarding, no peritoneal signs. Mildly dry mucous membranes but not clinically significantly dehydrated. Assessment is acute food poisoning, self-limiting gastroenteritis from likely contaminated food source. Prescribing oral rehydration solution for maintenance hydration. Metoclopramide 10 milligrams three times daily for anti-emetic control to facilitate oral rehydration. Antibiotics not indicated for uncomplicated food-borne illness. Advised return if bloody stools, persistent vomiting beyond 48 hours, inability to maintain oral intake, or signs of worsening dehydration.""",
        expected_diagnoses=["food poisoning"],
        expected_medications=["ORS", "metoclopramide"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 13. Worm infestation in child
    Encounter(
        name="Worm infestation in child",
        category="gi",
        conversation="""\
Mother: Doctor, my daughter keeps scratching her bottom, especially at night. She can't sleep properly because of it and she's very irritable.
Doctor: How old is she?
Mother: She's five.
Doctor: How long has this been going on?
Mother: About two weeks now. And yesterday I saw small white worms in her stool when I was cleaning the potty. I was so shocked and worried.
Doctor: That's actually very helpful for the diagnosis. The itching at night and the worms you described sound typical of threadworms, also called pinworms. They're very common in children, especially at this age, nothing to be embarrassed about. Let me check her tummy... it's soft, no pain when I press anywhere. She looks well otherwise, good energy. Temperature is 36.7, perfectly normal.
Mother: How did she get them?
Doctor: Usually from hand to mouth contact, playing in soil, touching contaminated surfaces and then eating without washing hands. I'm going to give her mebendazole, one 500 milligram tablet as a single dose now. We repeat it again in two weeks to catch any eggs that hatch in between. The whole family should be treated actually, to prevent re-infection. Make sure everyone washes their hands thoroughly, especially before eating and after using the toilet. Keep her fingernails short.
Mother: Is one tablet really enough?
Doctor: Yes, for threadworms a single dose works very well.""",
        dictation="""\
5 year old girl brought by mother, two week history of perianal pruritus worse at night causing sleep disturbance and irritability. Mother directly observed small white worms in child's stool yesterday confirming the diagnosis. General examination reveals a well child with normal activity levels. Abdomen soft, non-tender throughout, no organomegaly. Temperature 36.7, normal. Assessment is intestinal threadworm infestation, confirmed by maternal observation of characteristic Enterobius vermicularis in stool. Prescribing mebendazole 500 milligrams as a single oral dose with mandatory repeat dose in two weeks to address the worm lifecycle and prevent reinfection. Recommended that all household contacts receive simultaneous treatment. Hygiene counselling provided including thorough handwashing before meals and after toileting, keeping fingernails short, and regular laundering of bed linens. Good prognosis with appropriate treatment and hygiene measures.""",
        expected_diagnoses=["worm infestation"],
        expected_medications=["mebendazole"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 14. Bloody diarrhea / dysentery
    Encounter(
        name="Bloody diarrhea — dysentery",
        category="gi",
        conversation="""\
Patient: Doctor, I've had bad diarrhea for three days but today there was blood in it. I'm also having terrible stomach cramps and fever.
Doctor: How many stools per day?
Patient: At least ten yesterday. The blood started this morning, mixed in with the stool along with some mucus. It's getting worse.
Doctor: Let me check you. Your temperature is 38.6, you're properly febrile. Your abdomen is tender, especially in the lower left area. You look dehydrated, your lips are dry and cracked, and your pulse is 100.
Patient: I don't know where I got this from. The water in our area is not always clean and the pipes have been broken for weeks.
Doctor: The blood and mucus in the stool with fever and your exposure to potentially contaminated water points to dysentery, a bacterial gut infection. I need to start you on ciprofloxacin 500 milligrams twice a day for three days. And you need ORS urgently to replace the fluids you're losing. Take the full course of antibiotics even if you start feeling better. If the bleeding gets heavier or you can't keep fluids down at all, you need to go to the hospital.
Patient: Thank you, doctor. I've been suffering for days.""",
        dictation="""\
36 year old male, three day history of profuse diarrhea progressing to bloody stools with mucus since this morning. Reports more than ten stools daily. Severe abdominal cramping. Febrile. Reports exposure to potentially contaminated water supply with broken infrastructure in residential area. Temperature 38.6. Abdomen tender predominantly in left iliac fossa. Clinical dehydration present with dry cracked lips and tachycardia at pulse rate 100. Assessment is acute dysentery, likely bacterial aetiology given bloody mucoid diarrhea with systemic fever and epidemiological risk from contaminated water exposure. Commencing ciprofloxacin 500 milligrams twice daily for 3 day course as per standard dysentery management protocol. Oral rehydration solution prescribed for aggressive fluid replacement. Hospital referral indicated if patient unable to maintain adequate oral intake, increasing volume of rectal bleeding, or haemodynamic deterioration. Patient to complete full antibiotic course.""",
        expected_diagnoses=["acute gastroenteritis"],
        expected_medications=["ciprofloxacin", "ORS"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 15. Gastritis / acid reflux
    Encounter(
        name="Gastritis — epigastric burning",
        category="gi",
        conversation="""\
Patient: I've had this burning pain in my stomach for about two weeks. Right here in the middle, above my belly button. It gets worse after I eat, especially spicy food and acidic things.
Doctor: Any vomiting or blood in the stool?
Patient: No blood that I've noticed. I feel nauseous sometimes after eating but no actual vomiting.
Doctor: Do you smoke or drink alcohol?
Patient: I drink on weekends, maybe three or four beers each time. No smoking.
Doctor: Are you taking any anti-inflammatory tablets like ibuprofen or aspirin regularly?
Patient: No, nothing like that.
Doctor: Let me examine your tummy. There's tenderness right here in the epigastrium when I press. No masses, no guarding. The rest of the abdomen is soft and normal. Your temperature is 36.9. This sounds like gastritis, inflammation of the stomach lining. The alcohol and spicy food are likely aggravating factors.
Patient: What causes it exactly?
Doctor: Could be the alcohol, dietary irritants, stress, or sometimes a bacteria called H. pylori that lives in the stomach. I'm going to start you on omeprazole 20 milligrams once a day, take it in the morning before breakfast on an empty stomach. Take it for four weeks. Cut down on the alcohol, avoid very spicy food, and try eating smaller meals more frequently. If the symptoms persist after four weeks we may need to investigate further with a scope.
Patient: Thank you, doctor.""",
        dictation="""\
40 year old male, two week history of epigastric burning pain localized to the mid-epigastrium, worse postprandially particularly with spicy and acidic foods. Nausea present but no vomiting, no haematemesis, no melaena reported. Social alcohol use on weekends, approximately three to four beers per session. Non-smoker. Denies regular NSAID or aspirin use. Examination reveals epigastric tenderness on palpation without rebound or guarding. No palpable masses or organomegaly. Remainder of abdomen soft and non-tender. Temperature 36.9. Assessment is clinical gastritis, likely related to dietary factors and alcohol consumption, possible Helicobacter pylori contribution. Initiating omeprazole 20 milligrams once daily before breakfast for 4 week trial of proton pump inhibitor therapy. Lifestyle advice provided including alcohol reduction, avoidance of dietary irritants, and smaller frequent meals. If symptoms persist beyond trial period, will consider upper GI endoscopy for definitive evaluation.""",
        expected_diagnoses=["gastritis"],
        expected_medications=["omeprazole"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 16. Chronic diarrhea + metformin (wrong drug)
    Encounter(
        name="Chronic diarrhea — wrong drug metformin prescribed",
        category="gi",
        conversation="""\
Patient: Doctor, I've had loose stools almost every day for the past two months now. I've also lost about 5 kilos and my clothes don't fit anymore.
Doctor: Is there any blood in the stool?
Patient: No blood, just loose and watery, sometimes three or four times a day. Occasionally there's a bit of mucus.
Doctor: Any fever or vomiting?
Patient: No fever at all. Occasional nausea in the mornings but no actual vomiting.
Doctor: What about your appetite?
Patient: It's reduced quite a bit. I just don't feel like eating much. Food seems to go right through me.
Doctor: Are you taking any medications currently?
Patient: No, nothing.
Doctor: Let me examine you. Your abdomen is soft, no tenderness anywhere, no masses that I can feel. You do look like you've lost a fair bit of weight, your cheeks are a bit hollow. Your temperature is 37.0. Blood pressure is 118 over 72, that's normal. I'm going to start you on metformin 500 milligrams twice a day and we'll see if that helps settle the bowel down. Come back in two weeks and we'll reassess.
Patient: What is the metformin for exactly?
Doctor: It should help with your gut symptoms. Take it with food, morning and evening. If the diarrhea gets any worse or you notice blood, come back sooner.""",
        dictation="""\
50 year old female, two month history of chronic watery diarrhea with occasional mucus, frequency three to four stools daily. Significant unintentional weight loss of approximately 5 kilograms over same period with ill-fitting clothing and facial wasting noted. Reduced appetite throughout. No blood in stool, no fever, no vomiting. Not on any current medications. Examination shows abdomen soft, non-tender, no palpable masses or organomegaly. Evidence of weight loss on general inspection. Temperature 37.0. Blood pressure 118 over 72. Assessment is chronic diarrhea with significant weight loss, requires further investigation to exclude underlying pathology including malabsorption, inflammatory bowel disease, and occult malignancy. Prescribing metformin 500 milligrams twice daily. Follow-up in two weeks to reassess symptoms and consider further workup including stool studies and blood tests if no improvement.""",
        expected_diagnoses=["acute gastroenteritis"],
        expected_medications=["metformin"],
        expected_vitals=["temperature", "blood pressure"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Drug-Condition", "metformin"),
        ],
    ),

    # 17. Child with persistent vomiting — severe dehydration
    Encounter(
        name="Child persistent vomiting — severe dehydration",
        category="gi",
        conversation="""\
Mother: Please help, my baby can't keep anything down. She's been vomiting everything for two days now. Even breast milk comes right back up.
Doctor: How old is she?
Mother: Eighteen months.
Doctor: Has she had diarrhea as well?
Mother: Yes, watery diarrhea started yesterday. Maybe seven or eight times since then.
Doctor: Let me examine her urgently. Her eyes are very sunken, her mouth is completely dry, and look here, when I pinch her skin it stays up like a tent for several seconds. She's very lethargic, barely responding when I call her name. Her fontanelle is depressed. Temperature is 38.4 and her pulse is very fast at 160.
Mother: She was fine just three days ago, running around and playing. What happened?
Doctor: She has a severe stomach bug that's causing her to lose too much fluid through the vomiting and diarrhea. She's now severely dehydrated and we need to act fast. She needs an IV drip immediately to replace the fluid she's lost. Nurse, get a line in and start Ringer's lactate, 30 mls per kilogram in the first hour. Also start ORS by nasogastric tube if she still can't drink. This child may need transfer to the district hospital for continued care.
Mother: Is she going to survive?
Doctor: We're going to do everything we can right now. The fluids should help. We need to act quickly.""",
        dictation="""\
18 month old girl, two day history of persistent projectile vomiting including breast milk with no ability to retain any oral intake. Watery diarrhea commenced yesterday with approximately seven to eight episodes. Previously well and active child per mother. Examination reveals severely dehydrated infant with markedly sunken eyes, completely dry mucous membranes, significantly reduced skin turgor with tenting lasting several seconds on abdominal pinch, depressed anterior fontanelle, and obtunded affect with minimal response to stimulation. Temperature 38.4. Heart rate 160, significantly tachycardic for age. Assessment is severe acute gastroenteritis complicated by severe dehydration, constituting a medical emergency requiring immediate aggressive rehydration. Commencing intravenous Ringer's lactate at 30 millilitres per kilogram bolus over first hour as per WHO plan C protocol. Oral rehydration solution via nasogastric tube if oral route remains non-functional. This child requires close monitoring and likely transfer to district hospital for ongoing intravenous fluid management and observation.""",
        expected_diagnoses=["acute gastroenteritis"],
        expected_medications=["ORS"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("INFO", "Referral Suggestion", ""),
        ],
    ),

    # 18. Adult constipation
    Encounter(
        name="Adult constipation — elderly patient",
        category="gi",
        conversation="""\
Patient: Doctor, I haven't been able to go to the toilet properly for about ten days now. When I do manage to go, it's very hard and small, like little stones. My stomach feels bloated and uncomfortable.
Doctor: How old are you?
Patient: I'm seventy-two.
Doctor: How much water do you drink each day?
Patient: Not much, maybe two cups of tea during the day. I don't really like plain water.
Doctor: And your diet, do you eat much fruit and vegetables?
Patient: Not really. Mostly pap and bread and some meat when I can afford it. The vegetables are expensive.
Doctor: Are you taking any new medications?
Patient: Just the blood pressure tablets I've been on for years, nothing new.
Doctor: Let me examine your tummy. I can feel some fullness and firm stool in the left side. There's no pain when I press, no masses that worry me. Your bowel sounds are present but sluggish. Temperature is 36.8, normal. Blood pressure is 138 over 82, similar to usual for you. This is simple constipation, almost certainly from not drinking enough fluids and not having enough fibre in your diet. I'm going to give you lactulose syrup, 15 millilitres twice a day. It softens the stool and makes it easier to pass. But more importantly, you really need to drink more water, at least six glasses a day, and try to add more vegetables to your meals.
Patient: I'll try my best, doctor.""",
        dictation="""\
72 year old male, ten day history of constipation with passage of hard scybalous stools, associated abdominal bloating and discomfort. Dietary history reveals poor fluid intake limited to approximately two cups of tea daily and very low dietary fibre consisting mainly of refined starch with minimal fruit and vegetable intake. On chronic antihypertensive medication, no recent medication changes. Examination shows mildly distended abdomen with faecal loading palpable in the left iliac fossa, non-tender. No palpable masses or organomegaly. Bowel sounds present but reduced in frequency. Temperature 36.8. Blood pressure 138 over 82. Assessment is functional constipation secondary to inadequate fluid and dietary fibre intake. Prescribing lactulose 15 millilitres twice daily as an osmotic stool softener. Detailed dietary counselling provided emphasizing need for at least six glasses of water daily and increased fruit and vegetable consumption. No red flag features requiring further investigation at this point.""",
        expected_diagnoses=["constipation"],
        expected_medications=["lactulose"],
        expected_vitals=["blood pressure"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # MALARIA / FEBRILE ILLNESS (6)
    # ═══════════════════════════════════════════════════════════════════════

    # 19. Uncomplicated malaria adult
    Encounter(
        name="Uncomplicated malaria adult",
        category="malaria",
        conversation="""\
Patient: Doctor, I've been having terrible shaking episodes for two days now. I feel cold then suddenly very hot and drenched in sweat. My head is pounding something terrible.
Doctor: Do you live in a malaria area?
Patient: Yes, near the river. We had a lot of rain recently and the mosquitoes have been very bad this season.
Doctor: Any vomiting or diarrhea?
Patient: I vomited once yesterday but nothing today. My joints and muscles ache all over, even my bones are sore.
Doctor: Let me check you. Your temperature is 39.0, that's quite high. You're sweating now. Let me do a rapid test from your finger... it's positive for P. falciparum. Let me feel your tummy... your spleen is slightly enlarged. But you're conscious, talking clearly to me, no confusion, which is reassuring.
Patient: Is it bad?
Doctor: It's malaria but it's uncomplicated, meaning it hasn't affected your brain or vital organs. I'm giving you artemether-lumefantrine, the standard combination treatment. Take four tablets now, four more in eight hours, then four tablets twice a day for the next two days to complete the course. Take them with food or milk for better absorption. I'm also giving you paracetamol 1 gram three times a day for the fever and pain.
Patient: Thank you, doctor. I should have been using my mosquito net properly.""",
        dictation="""\
32 year old male residing in malaria endemic area near river, two day history of classic malarial periodicity with rigors, profuse sweating episodes, and severe headache. Associated myalgia and arthralgia. Single episode of vomiting yesterday, currently tolerating oral intake. Lives in area with recent heavy rainfall and increased mosquito density. Temperature 39.0. Malaria rapid diagnostic test positive for Plasmodium falciparum. Mild splenomegaly palpable on abdominal examination. No features of severe or complicated malaria present including no altered consciousness, no respiratory distress, no prostration, and no clinical jaundice. Assessment is uncomplicated falciparum malaria. Commencing artemether-lumefantrine standard 6-dose course administered with fatty food for optimal absorption. Paracetamol 1 gram three times daily for fever and symptomatic pain relief. Counselled on importance of completing full course. Advised on mosquito net use for prevention and to return if vomiting prevents oral medication or symptoms worsen.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "paracetamol"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    # 20. Uncomplicated malaria child
    Encounter(
        name="Uncomplicated malaria child",
        category="malaria",
        conversation="""\
Mother: My son has had a very high fever since yesterday. He's been shivering badly and then sweating through his clothes. He won't eat anything at all.
Doctor: How old is he?
Mother: He's seven years old. We live near the dam and he plays outside a lot in the evenings when the mosquitoes come out.
Doctor: Let me check his temperature... 39.5, that's quite high for a child. I'm going to prick his finger for a rapid malaria test. Let's wait a moment for the result... it's positive. Let me feel his tummy, his spleen is not enlarged which is good. He's alert and responsive, talking to me, which is reassuring. His oxygen is 97 percent, that's normal.
Mother: Is he going to be okay?
Doctor: Yes, we've caught it in time. It's uncomplicated malaria, meaning it hasn't spread to the brain or other organs. I'm going to give him artemether-lumefantrine at the dose adjusted for his weight. He weighs 22 kilos so it's two tablets now, two more in eight hours, then two tablets twice a day for two more days. Give them with food or a glass of milk. I'm also giving paracetamol syrup for the fever. If he starts vomiting the tablets or becomes confused or drowsy, or the fever doesn't come down in two days, bring him back here immediately.
Mother: Thank you, doctor. I'll watch him very closely at home.""",
        dictation="""\
7 year old boy, one day history of high grade fever with rigors and profuse sweating, complete anorexia. Lives near dam with regular evening outdoor exposure during peak mosquito activity hours. Temperature 39.5 on examination. Malaria rapid diagnostic test positive. Abdominal examination reveals no splenomegaly. Child is alert, responsive, and oriented, maintaining normal conversation. Pulse oximetry 97 percent on room air, satisfactory. No features of severe malaria identified including no altered consciousness, no convulsions, no prostration, no respiratory distress, no clinical jaundice, and no severe anaemia. Assessment is uncomplicated falciparum malaria in a paediatric patient. Commencing artemether-lumefantrine at weight-adjusted dosing for 22 kilogram child, standard three day treatment course. Paracetamol syrup prescribed for fever management. Mother educated on danger signs for severe malaria requiring immediate return including persistent vomiting, confusion, excessive drowsiness, convulsions, or inability to eat and drink. Follow-up if fever persists beyond 48 hours of treatment.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "paracetamol"],
        expected_vitals=["temperature", "oxygen"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    # 21. Fever workup negative
    Encounter(
        name="Fever workup negative — no localizing signs",
        category="malaria",
        conversation="""\
Patient: I've had a fever for three days now, doctor. It comes and goes throughout the day. I feel weak and achy all over but I can't pinpoint anything specific that's wrong.
Doctor: Any cough, sore throat, or runny nose?
Patient: No, nothing like that.
Doctor: Burning when you pass urine or going more frequently?
Patient: No, urine is fine.
Doctor: Diarrhea or vomiting?
Patient: No, my stomach is okay. I'm just not very hungry.
Doctor: Headache?
Patient: A mild one that comes and goes but nothing severe.
Doctor: Let me examine you thoroughly. Temperature is 38.3. Your throat looks normal, no redness. Chest is clear on both sides. Tummy is soft, no tenderness anywhere. No rash on your body. No joint swelling. Let me check the malaria rapid test... it's negative. Urine dipstick is also normal, no infection there. I can't find a clear source for this fever.
Patient: So what do I do then?
Doctor: I'm going to give you paracetamol for the fever and body aches, take 1 gram three times a day. I want you to come back in 48 hours so I can reassess you. Sometimes viral infections cause a fever without obvious localizing signs and they resolve on their own within a few days. But if you develop new symptoms like a bad headache, stiff neck, a rash, confusion, or if the fever goes above 39.5, come back sooner than the two days.
Patient: Okay, doctor. I hope it goes away.""",
        dictation="""\
28 year old female, three day history of intermittent fever with generalized malaise, mild body aches, and mild intermittent headache. No respiratory symptoms including no cough, sore throat, or rhinorrhea. No urinary symptoms. No gastrointestinal symptoms. Reduced appetite but tolerating fluids. Temperature 38.3 on examination. Complete examination performed with no localizing signs identified. Oropharynx normal. Chest clear bilaterally. Abdomen soft, non-tender, no organomegaly. No skin rash or petechiae. No joint swelling or tenderness. Malaria rapid diagnostic test negative. Urine dipstick analysis within normal limits with no leucocytes or nitrites. Assessment is pyrexia of unknown origin, most likely self-limiting viral aetiology in the absence of localizing features. Prescribing paracetamol 1 gram three times daily for symptomatic fever and pain management. Plan for clinical review in 48 hours for reassessment. Comprehensive safety net advice provided regarding red flag symptoms including severe headache, neck stiffness, new rash, confusion, or high spiking fever.""",
        expected_diagnoses=["fever"],
        expected_medications=["paracetamol"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 22. Typhoid suspect
    Encounter(
        name="Typhoid suspect — prolonged fever",
        category="malaria",
        conversation="""\
Patient: I've been sick for over a week now, doctor. The fever just won't go away no matter what I do. I also have a bad headache and my stomach is sore and bloated.
Doctor: Tell me more about the fever pattern. Does it change during the day?
Patient: It seems to go up in the afternoon and evening, getting quite high, then comes down a bit by morning but it never goes away completely. Each day it feels a bit worse than the day before.
Doctor: Any diarrhea or constipation?
Patient: Actually I've been constipated for the past few days which is unusual for me. And I feel very bloated.
Doctor: Any rash anywhere on your body?
Patient: I noticed some small pink spots on my chest yesterday that weren't there before.
Doctor: Let me examine you. Temperature is 39.4, quite high. I can see a few faint salmon-coloured spots on your trunk, those are significant. Your abdomen is tender in the right lower area and I can feel your spleen is enlarged. With the stepladder fever pattern going up each day, the rose spots on the skin, the splenomegaly, and the abdominal symptoms, I'm strongly suspicious of typhoid. The malaria test is negative which rules that out.
Patient: Typhoid? How did I get it?
Doctor: Usually from contaminated food or water. I'm going to start you on ciprofloxacin 500 milligrams twice a day for seven days. We'll also send blood for a Widal test to help confirm. Rest and drink plenty of clean fluids.
Patient: Thank you, doctor.""",
        dictation="""\
40 year old male, more than one week history of persistent fever with characteristic stepladder pattern worsening daily, peaking in afternoons and evenings with incomplete resolution by morning. Severe headache throughout. Constipation for several days, associated abdominal bloating. Reports new pink spots on chest yesterday. Temperature 39.4. Inspection reveals faint salmon-coloured rose spots on anterior trunk. Abdominal tenderness in right iliac fossa. Splenomegaly palpable below left costal margin. Malaria RDT negative. Clinical picture strongly suggestive of enteric typhoid fever based on classic constellation of stepladder fever, rose spots, splenomegaly, right iliac fossa tenderness, and constipation. Commencing ciprofloxacin 500 milligrams twice daily for 7 day course. Blood samples obtained for Widal test serological confirmation. Advised bed rest and adequate hydration with clean water.""",
        expected_diagnoses=["typhoid fever"],
        expected_medications=["ciprofloxacin"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[],
    ),

    # 23. Malaria with wrong drug (atenolol)
    Encounter(
        name="Malaria — wrong drug atenolol added",
        category="malaria",
        conversation="""\
Patient: Doctor, I'm having these terrible fevers and shaking. It started three days ago and I can't keep food down. I vomited twice today already.
Doctor: Where do you live? Have you been anywhere recently?
Patient: I'm from the village near the nature reserve. There are lots of mosquitoes there, especially now during the rains.
Doctor: Let me check you. Your temperature is 39.8, that's very high. I'm doing the rapid test now from your finger... it's positive for malaria. You're sweating heavily. Let me feel your tummy... your spleen is a bit enlarged, I can feel the edge. Your blood pressure is 130 over 80, pulse is 88.
Patient: Please help me, doctor. I feel very sick and weak.
Doctor: It's malaria but there are no signs of severe disease, which is good. I'm going to give you artemether-lumefantrine, the malaria treatment combination. Take four tablets now with some food and then the full course over three days. I'm also going to prescribe you atenolol 50 milligrams once a day to take with it. And paracetamol 1 gram three times daily for the fever and body pains.
Patient: What's the atenolol for?
Doctor: Just take it, it's part of the treatment. You'll feel better soon. Make sure you eat something with the malaria tablets.""",
        dictation="""\
38 year old male residing in rural endemic area near nature reserve, three day history of febrile illness with rigors, profuse sweating, and vomiting twice today. Living in area with high mosquito density during current rainy season. Temperature 39.8 on examination. Malaria rapid diagnostic test positive for falciparum species. Clinical examination reveals splenomegaly with palpable splenic edge. Blood pressure 130 over 80, heart rate 88 per minute, regular. Patient is alert and oriented with no features of severe or complicated malaria including no altered consciousness, no seizure activity, no prostration, and no severe anaemia. Assessment is uncomplicated falciparum malaria. Commencing artemether-lumefantrine standard treatment course to be taken with fatty food. Additionally prescribing atenolol 50 milligrams once daily. Paracetamol 1 gram three times daily for antipyretic and analgesic effect. Patient advised to return if unable to tolerate oral medications due to persistent vomiting or if clinical condition worsens.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine", "atenolol", "paracetamol"],
        expected_vitals=["temperature", "blood pressure"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("WARNING", "Drug-Condition", "atenolol"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),

    # 24. Recurrent malaria
    Encounter(
        name="Recurrent malaria — third episode this year",
        category="malaria",
        conversation="""\
Patient: Doctor, the malaria is back again. This is the third time this year already. I know the symptoms by now — the shaking, the sweating, the terrible headache. It started two days ago.
Doctor: I see from your file you were treated here in February and again in May. You're in the same area still?
Patient: Yes, I live and work near the wetlands. I'm a farmer. I use a net at night but the mosquitoes get me during the day when I'm out in the fields working.
Doctor: Let me check you. Temperature is 38.9. The rapid test is positive again for falciparum. Your spleen is definitely bigger than last time I examined you. And you look a bit pale, let me check your eyes... yes, your conjunctivae are pale which worries me about anemia from these recurrent episodes.
Patient: My wife says I look yellowish too, especially my eyes.
Doctor: I can see mild jaundice in your sclerae. I'm going to treat you with artemether-lumefantrine again, the full course as before. But we need to have a serious conversation about prevention this time. Three episodes in one calendar year is too many and it's taking a toll on your body. I want to refer you to the district hospital to discuss prophylaxis options and importantly to check your full blood count because repeated malaria destroys red blood cells and can cause significant anemia.
Patient: Whatever you say, doctor. I'm tired of getting sick all the time. It's affecting my farming.""",
        dictation="""\
35 year old male subsistence farmer, third documented episode of malaria this calendar year following previous treatments in February and May. Lives and works near wetlands with significant daytime mosquito exposure despite bed net use at night. Two day history of recurrent febrile illness with rigors, sweating, severe headache. Temperature 38.9. Malaria RDT positive for Plasmodium falciparum. Progressive splenomegaly noted compared to previous examinations. Conjunctival pallor present raising concern for developing anaemia secondary to recurrent haemolysis. Mild scleral icterus observed. No features of severe complicated malaria. Assessment is recurrent uncomplicated falciparum malaria, third episode in twelve months, with clinical signs of evolving chronic haemolytic anaemia. Treating with artemether-lumefantrine standard course. Referral to district hospital for full blood count to quantify anaemia and discussion of chemoprophylaxis strategies given occupational exposure risk.""",
        expected_diagnoses=["malaria"],
        expected_medications=["artemether-lumefantrine"],
        expected_vitals=["temperature"],
        patient_allergies=[],
        expected_dangers=[
            _d("WARNING", "Triage", "WORRISOME"),
            _d("INFO", "Lab Recommendation", ""),
        ],
    ),
]
