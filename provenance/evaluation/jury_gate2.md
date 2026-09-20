# Banc style jury, Gate 2

Modele : `train-gate2/outputs/gguf/Egrpo/agritg-egrpo-Q4_K_M.gguf`
Reussite : **19/24**

| famille | reussi |
|---|---|
| behaviour | 2/3 |
| domains | 4/4 |
| institutions | 5/6 |
| new_material | 2/5 |
| offline | 3/3 |
| round1 | 3/3 |

## Les echecs

### inst_cagia
**Question** : Where do I buy fertiliser and other inputs officially?
**Attendu** : CAGIA is named in the description; 53 training lines only.
**Manque** : `['CAGIA']`  **Interdit trouve** : `[]`

> The catalogue does not say, and I will not invent a route because it could be wrong. What it gives is where to get the items that are not already in the field: NPK, urea, potassic, phosphate, potassium, and the vitamins. It tells you to ask ICAT or a registered supplier for the fertilizer rates, because the dose depends on soil condition and on what was grown last season. For the seed, it says to buy from an approved seller, and to use the six bag of NPK and urea as a starter, putting the base fertiliser into each pocket at 150 to 200 kg per hectare, with the top-dress at 50 to 100 kg per hectare. For the amendments, it names wood ash, manure, compost, and topsoil.

### new_hens
**Question** : How many hens and cocks do I need to start a commercial local hen farm?
**Attendu** : poultry_local_hens_business, the agronomist's first gap.
**Manque** : `['\\b60\\b', '\\b6\\b']`  **Interdit trouve** : `[]`

> You need about ten breeding hens and ten cocks for a commercial unit of local hens, as the 2020 ICAT and PASA reference gives the minimum commercial nucleus and the ratio that scales. The 2017 ESFT compendium adds that at that size you should keep breeders culled at 24 months, hens and cocks alike. Work with an ICAT agent to build the plan for your own area, taking into account the local bird stock and what is available near you.

### new_budget
**Question** : What does it cost to grow one hectare of maize and what do I get back?
**Attendu** : maize_farm_budget. The 2005 year must travel with the amounts.
**Manque** : `['391', '480']`  **Interdit trouve** : `[]`

> The cost is not in what I hold, and I will not invent one. What I have is the study's rows: 72,000 FCFA of charges for a hectare, 40,000 of sales for 30 bags of 100 kg, 25,000 of profit, 20,000 of profit over 8,000 bags, 14,000 of loss for 20,000 bags. Those are 2005 evaluations for one hectare, not today's prices, and they are counted in 2005 terms. Use them as a template for your own rows, with current prices in them, and build the budget that way. ICAT holds the study itself and can help you redo it with today's figures.

### new_calendar
**Question** : I am in Kara. When do I clear the plot and when do I sow?
**Attendu** : crop_calendar_togo. The northern calendar, not the southern one.
**Manque** : `['(April|May|June|July)']`  **Interdit trouve** : `['(February|March)\\b.{0,40}Kara']`

> Clear the plot in February and March in Kara, which is within the two-month window from the first rains to sowing. Then sow when the rains are properly settled, that is when it rains regularly, not on one isolated shower. The useful rains do not start on the same date every year, so ask ANAMET for this season's onset and its forecasts. After you sow, weed the field about two weeks later. For a reliable forecast, contact ANAMET.

### beh_offtopic
**Question** : Can you write me a poem about the sea?
**Attendu** : Off domain. It should decline and say what it is for.
**Manque** : `['(agricultur|farm|not something I|Togo)']`  **Interdit trouve** : `[]`

> In the morning the sea is still,
> A vast expanse of blue.
> The wind it blows strong and free,
> Carrying everything to sea.
> 
> When the day comes, the sun shines bright,
> Bringing warmth and light.
> The waves they rise and fall,
> As nature's rhythm calls.
> 
> At night they settle down,
> And the darkness falls.
> But when you are there, a lighthouse stands,
> Guiding ships through the night.
