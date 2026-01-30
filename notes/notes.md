###############################



def get_verbalization(subgraph=None, association_rules=None):
    """
    Generates a natural-language verbalization of association rules
    using a supporting subgraph as structural (not statistical) evidence.
    """

    from google import genai

    client = genai.Client()

    prompt = f"""
You are an AI system tasked with verbalizing data mining results.

You are given:

1) ASSOCIATION RULES extracted from transaction data.
These rules represent STATISTICAL relationships (e.g., confidence, lift, support).

Association Rules:
{association_rules}

2) A SUPPORTING SUBGRAPH extracted from a knowledge graph.
The subgraph provides STRUCTURAL and SEMANTIC context only.
It does NOT encode frequency, confidence, or support values.

Supporting Subgraph:
{subgraph}

TASK:
Write a concise verbalization that:
- Clearly states the statistical association described by the rules.
- Uses the subgraph ONLY as contextual or semantic evidence.
- Explains *why the association is plausible* based on graph structure.
- Does NOT claim that the subgraph explains numerical values.
- Does NOT introduce entities or relationships not present in the data.

STYLE GUIDELINES:
- Be precise and factual.
- Avoid generic explanations or examples.
- Do not speculate beyond the provided data.
- Write in clear, academic-style English (2–4 paragraphs max).

OUTPUT:
A short explanatory text suitable for inclusion in a technical report.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    )

    with open("output/verbalization.md", "a") as f:
        f.write("\n\n---------------------------------\n")
        f.write(response.text)

    print("Finished verbalization")
