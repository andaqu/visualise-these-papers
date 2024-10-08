import requests
import json
import networkx as nx
import itertools
from flask import Flask, send_file
import os
from dotenv import load_dotenv
import logging

# Initialize Flask app
app = Flask(__name__)

with open('canvas.html', 'r') as file:
    CANVAS_CONTENT = file.read()

logging.basicConfig(filename='server.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv() 

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

def query_notion_database():
    logger.info("Querying Notion database...")
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers)

    if response.status_code != 200:
        logger.error(f"Failed to query Notion database: {response.status_code} - {response.text}")
        response.raise_for_status()
    
    data = response.json()
    logger.info("Successfully queried Notion database.")
    return data

def parse_notion_data(data):
    logger.info("Parsing Notion data...")
    categories_colors = {}
    papers_dict = {}
    
    for result in data.get("results", []):
        try:
            page_id = result["properties"]["Name"]["title"][0]["text"]["content"]
            title = result["properties"]["Title"]["rich_text"][0]["text"]["content"]
            link = result["properties"]["Name"]["title"][0]["text"]["link"]["url"]
            categories = [cat["name"] for cat in result["properties"]["Categories"]["multi_select"]]
            current_categories_colors = {cat["name"]: cat["color"] for cat in result["properties"]["Categories"]["multi_select"]}
        except Exception as e:
            logger.warning(f"Skipping result due to error: {e}")
            continue

        for category, color in current_categories_colors.items():
            if category not in categories_colors:
                if color == "default":
                    color = "black"
                categories_colors[category] = color
        
        goal = result["properties"]["Goal"]["rich_text"][0]["text"]["content"]
        papers_dict[page_id] = {
            'categories': categories,
            'title': title,
            'link': link,
            'goal': goal
        }
    
    logger.info("Parsed Notion data successfully.")
    return papers_dict, categories_colors

def create_weighted_graph(papers_dict):
    logger.info("Creating weighted graph...")
    G = nx.Graph()
    for paper, attributes in papers_dict.items():
        node_size = len(attributes['categories']) * 10
        G.add_node(paper, categories=attributes['categories'], title=attributes['title'], link=attributes['link'], goal=attributes['goal'], size=node_size)

    papers = list(papers_dict.keys())
    for paper1, paper2 in itertools.combinations(papers, 2):
        shared_categories = set(papers_dict[paper1]['categories']) & set(papers_dict[paper2]['categories'])
        if shared_categories:
            G.add_edge(paper1, paper2, weight=len(shared_categories))

    G.remove_nodes_from(list(nx.isolates(G)))
    logger.info("Weighted graph created successfully.")
    return G

def visualize_weighted_graph(G, categories_colors):
    logger.info("Visualizing weighted graph...")
    from pyvis.network import Network

    # Generate a unique HTML file name to avoid conflicts
    html_file_name = "notion_weighted_graph.html"

    net = Network(notebook=False, height="750px", width="100%", directed=False)
    for node, attrs in G.nodes(data=True):
        categories = ", ".join(attrs['categories'])
        title = attrs.get('title', 'Unknown Title')
        goal = attrs.get('goal', 'No goal provided')
        link = attrs.get('link', '#')
        net.add_node(node, label=node, categories_data=f"{categories}", title_data=title, goal_data=goal, link_data=link, font={'size': 35, 'color': 'rgba(0, 0, 0, 0.7)'})

    for edge in G.edges(data=True):
        weight = edge[2]['weight']
        net.add_edge(edge[0], edge[1], value=weight, title=f"Shared categories: {weight}")

    net.set_options("""{ "physics": { "enabled": true, "barnesHut": { "gravitationalConstant": -30000, "centralGravity": 0.3, "springLength": 600, "springConstant": 0.04, "avoidOverlap": 0.5, "damping": 0.09 }, "minVelocity": 0.75 }}""")
    net.save_graph(html_file_name)

    with open(html_file_name, "a") as f:
        f.write(f"<script>var categoriesColors = {json.dumps(categories_colors)};</script>")

    with open(html_file_name, "a") as f:
        f.write(CANVAS_CONTENT)

    logger.info("Weighted graph visualized successfully.")
    return html_file_name

@app.route('/')
def serve_html():
    logger.info("Serving HTML page...")
    # Query data and create graph
    notion_data = query_notion_database()
    papers_dict, categories_colors = parse_notion_data(notion_data)
    G = create_weighted_graph(papers_dict)
    html_file_name = visualize_weighted_graph(G, categories_colors)

    # Serve the dynamically generated HTML file
    return send_file(html_file_name)

if __name__ == '__main__':
    app.run(port=42528)
