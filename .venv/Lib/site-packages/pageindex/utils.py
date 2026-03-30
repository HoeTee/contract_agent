import openai
import textwrap
from pprint import pprint

async def call_llm(prompt, api_key, model="gpt-4.1", temperature=0):
    """Call an LLM to generate a response to a prompt"""
    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()

def remove_fields(data, fields=['text'], max_len=None):
    if isinstance(data, dict):
        return {k: remove_fields(v, fields, max_len) for k, v in data.items() if k not in fields}
    elif isinstance(data, list):
        return [remove_fields(item, fields, max_len) for item in data]
    elif isinstance(data, str):
        return data[:max_len] + '...' if max_len is not None and len(data) > max_len else data
    return data

def print_tree(tree, exclude_fields=['text', 'page_index']):
    cleaned_tree = remove_fields(tree.copy(), exclude_fields, max_len=40)
    pprint(cleaned_tree, sort_dicts=False, width=100)

def print_wrapped(text, width=100):
    for line in text.splitlines():
        print(textwrap.fill(line, width=width))

def create_node_mapping(tree, include_page_ranges=False, max_page=None):
    """
    Create a mapping of node_id to node for quick lookup.
    
    Args:
        tree: The document tree structure
        include_page_ranges: If True, also include page range information
        max_page: The maximum page number of the document (used for the last node's end_index)
        
    Returns:
        dict: If include_page_ranges=False, returns {node_id: node}
              If include_page_ranges=True, returns {node_id: {"node": node, "start_index": start, "end_index": end}}
    """
    def get_all_nodes(tree):
        if isinstance(tree, dict):
            return [tree] + [node for child in tree.get('nodes', []) for node in get_all_nodes(child)]
        elif isinstance(tree, list):
            return [node for item in tree for node in get_all_nodes(item)]
        return []
    
    all_nodes = get_all_nodes(tree)
    
    if not include_page_ranges:
        return {node["node_id"]: node for node in all_nodes if node.get("node_id")}
    
    # Include page ranges
    mapping = {}
    for i, node in enumerate(all_nodes):
        if node.get("node_id"):
            start_page = node["page_index"]
            
            # Get the next node's page_index
            if i + 1 < len(all_nodes):
                next_node = all_nodes[i + 1]
                end_page = next_node.get("page_index")
            else:
                # This is the last node - use max_page if provided
                end_page = max_page
            
            mapping[node["node_id"]] = {
                "node": node,
                "start_index": start_page,
                "end_index": end_page
            }
    
    return mapping