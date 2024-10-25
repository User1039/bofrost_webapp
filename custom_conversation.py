
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv
import os
import json
from pprint import pprint

import random
filter_overview = {
    "Schwierigkeit" : [
        "leicht",
        "mittel",
        "schwer"
    ],
    "Eigenschaften" : [
        "Ohne Lactose",
        "Ohne Fisch",
        "Ohne Rindfleisch",
        "Ohne Gluten",
        "vegan",
        "Ohne Meeresfrüchte",
        "Ohne Fleisch",
        "Ohne Geflügel",
        "vegetarisch",
        "Ohne Wildfleisch",
        "Ohne Schwein"
    ],
    "Schlüsselwoerter" : [
        "Aufläufe und Überbackenes",
        "Beilage",
        "bofrost*free",
        "Eis",
        "Familie",
        "Frühling",
        "Frühstück",
        "Getränke",
        "grillen",
        "gut vorzubereiten",
        "Halloween",
        "Hauptgericht",
        "Herbst",
        "Kinderleicht",
        "Kuchen und Gebäck",
        "Länderküche",
        "Muttertag",
        "Nachtisch",
        "Oktoberfest",
        "Ostern",
        "Party",
        "Sommer",
        "Valentinstag",
        "Vorspeise",
        "Weihnachten",
        "Winter"
    ],
    "Zutaten" : [],
}



retrieval_system_prompt_template = """\
Du bist hilfreicher Assistent, welcher damit beauftragt ist Anfragen in natürliche Sprache in JSON Filter zu übersetzen.
Dir stehen folgende Filter zur Auswahl:
{filter_overview}

Dein Antwort muss ausschliesslich aus JSON im Format wie im obigen Beispiel gegeben sein. \
Falls ein Feld nicht benötigt wird, muss es leer gelassen werden, anstatt es zu entfernen. \
Für das Eigenschaften Feld, gib bitte hier nur Werte an, wenn der Nutzer aktiv bestimmte Komponenten ausschliessen möchte. \
Einen Speziallfall bildet das Zutaten Feld. Hier gibt es keine vorgegebenen Werte. Stattdessen, nutze die Zutaten die der Nutzer explizit erwähnt. \

Ignoriere Rechtschreibfehler des Nutzers, solange du dir sehr sicher bist dass du die Intention des Nutzers verstehst.\
"""

generation_system_prompt_template = """\
Du bist ein hilfreicher Assistent, welcher eine Konversation mit dem Nutzer führt. \
Der Nutzer ist auf der Suche nach Rezepten. \
Wir haben bereits die zu seiner Anfrage passenden Rezepte gefunden. Du sollst diese nun in eine Antwort an den Nutzer verpacken. \
Bleibe dabei jedoch prägnant. Anstatt die Quellen direkt zu nennen, erwähne sie durch ein [docx] im Text, wobei das x durch den Rezept Index ersetzt werden soll.\
Es sollte insbesondere keine stumpfe Auflistung der Zutaten oder Schlüsselwörter sein.

Gefundene Rezepte:
{sample_recipes}

Wichitig: Anstatt die Quellen direkt zu nennen, erwähne sie durch ein [docx] im Text, wobei das x durch den Rezept Index ersetzt werden soll. \
Falls keine Rezepte gefunden wurden, gib bitte eine entsprechende Nachricht zurück.\
"""

import json
class RecipeDataset:
    def __init__(self, data : list[dict]):
        self.data = data

    def _ingredient_match (self, ingredient_list, search_terms):
        # Search term is a list of strings
        # Ingredient list is a list of strings
        # Returns True if all search terms are in the ingredient list
        # need only partial matches. E.g. "Tomato" should match "Tomato Sauce"

        for term in search_terms:
            found = False
            for ingredient in ingredient_list:
                if term.lower() in ingredient.lower():
                    found = True
                    break
            if not found:
                return False
        return True

    def search_recipes(self, zutaten=None, schluesselwoerter=None, schwierigkeit=None, eigenschaften=None):
        results = self.data

        if zutaten:
            results = [r for r in results if self._ingredient_match(r["Zutaten"],zutaten)]
        if schluesselwoerter:
            results = [r for r in results if all(k in r['Schlüsselwörter'] for k in schluesselwoerter)]
        if schwierigkeit:
            results = [r for r in results if r['Schwierigkeit'] == schwierigkeit]
        if eigenschaften:
            results = [r for r in results if all(e in r['Eigenschaften'] for e in eigenschaften)]

        return results

with open('recipes.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
dataset = RecipeDataset(data)


from pydantic import BaseModel

class Citation(BaseModel):
    content : str
    title : str = ''
    url : str = ''
    filepath : str = ''
    chunk_id : str = 'Test ChunkID'

class Context(BaseModel):
    citations : list[Citation]
    intent : str = ''
    all_retrieved_documents : list[str] = ''

def format_recipes_to_context(recipes):
    citations = []
    for recipe in recipes:
        recipe_content = ''
        if image_url := recipe.get("Bild_URL",''):
            recipe_content += f"![Bild]({image_url}) \n\n"

        if url := recipe.get("URL",''):
            recipe_content += f"[Quelle]({url})\n\n"

        recipe_content += f'**Zutaten:**\n\n'
        for zutat in recipe['Zutaten']:
            recipe_content += f'- {zutat}\n'

        # if kategorie := recipe.get("Rezeptkategorie",''):
        #     recipe_content += f'\n**Kategorie:** {kategorie}\n'

        citation = Citation(
            content = recipe_content,
            title = recipe["Name"],
            url = recipe["URL"],
            filepath=recipe["Name"],
        )
        citations.append(citation)
    return Context(citations=citations)

# print(load_dotenv())
async def handle_custom_conversation(messages : list[dict]):
    # print(os.getenv("AZURE_OPENAI_ENDPOINT"))
    client = AsyncAzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        api_version='2024-02-01'
        # api_version=os.getenv("AZURE_OPENAI_API_VERSION")
    )
    # print(os.getenv("AZURE_OPENAI_MODEL"))
    completion = await client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_MODEL"),
        messages=[
            {"role": "system", "content": retrieval_system_prompt_template.format(filter_overview = json.dumps(filter_overview))},
        ] + messages,
        temperature=0.0,
    )
    filters_string = completion.choices[-1].message.content.replace("```json", "").replace("```", "")
    filters = json.loads(filters_string)
    filters_converted = {k.lower().replace("ü","ue") : v for k, v in filters.items()}
    pprint(filters_converted)
    results = dataset.search_recipes(**filters_converted)

    sampled_results = random.sample(results, min(3, len(results)))
    for index, recipe in enumerate(sampled_results):
        recipe['Index'] = index+1
    # 
    # pprint(sampled_results)

    # Baue jetzt die Anfrage so, dass die gefundenen Rezepte in eine Antwort an den Nutzer verpackt werden.
    
    # pprint([
    #         {"role": "system", "content": generation_system_prompt_template.format(sample_recipes = json.dumps(sampled_results))},
    #     ] + messages)

    sample_recipes_filtered = [
        {k:v for k,v in recipe.items() if k in ['Name','Zutaten','Rezeptkategorie',"Schlüsselwörter"]} for recipe in sampled_results
    ]
    completion =  await client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_MODEL"),
        messages=[
            {"role": "system", "content": generation_system_prompt_template.format(sample_recipes = json.dumps(sampled_results))},
        ] + messages,
        temperature=0.0,
    )
    completion.choices[0].message.context = format_recipes_to_context(sampled_results).model_dump()
    return {
        "chatCompletion" : completion,
        "history_metadata" : {},
        "apim_request_id" : "jucktmichnicht"
    }


