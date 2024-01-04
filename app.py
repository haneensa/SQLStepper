import duckdb
from flask import Flask, request
from flask_cors import CORS
import pandas as pd
import io

from smokedduck_lineage import extractMetadata, runQuery, serializeLineage, addDelimJoinAnnotation

app = Flask(__name__)
CORS(app)
client_connections = {}


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'  # Replace '*' with your desired origin or origins
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, client_id'
    return response

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


def DropLineageTables(con: duckdb.DuckDBPyConnection):
    tables = con.execute("PRAGMA show_tables").fetchdf()
    # TODO: clear in-mem lineage
    for index, row in tables.iterrows():
        if row["name"][:7] == "LINEAGE":
            print("drop: ", row["name"])
            con.execute("DROP TABLE "+row["name"])
    con.execute("pragma clear_lineage")

@app.post("/sql")
def execute_sql():
    body = request.json
    client_id = request.json.get('client_id')
    query = body['query']
    print(client_id, query)

    con = client_connections[client_id]

    df, qid, plan = runQuery(con, query)
    
    addDelimJoinAnnotation(plan)
    extractMetadata(con, qid, plan, 0)
    lineage_json = serializeLineage(qid, plan, 0, {})
    lineage_json["qstr"] = query 
    # drop all lineage tables
    #print("*****", lineage_json)
    DropLineageTables(con)
    return lineage_json

@app.post("/csv")
def execute_csv():
    body = request.json
    table_name = body['name']
    csv = body['csv']
    
    client_id = request.json.get('client_id')
    con = client_connections[client_id]
    
    df = pd.read_csv(io.StringIO(csv))
    print("Register:", table_name, df)
    file_name = "{}.csv".format(table_name)
    df.to_csv(file_name, encoding='utf-8',index=False)
    con.execute("CREATE TABLE {} AS SELECT * FROM '{}';".format(table_name, file_name))
    print("Create table: {} with data {}".format(table_name, df))
    return ""

@app.post("/schema")
def execute_schema():
    client_id = request.json.get('client_id')
    if client_id not in client_connections:
        print("init db for {}".format(client_id))
        con = duckdb.connect(database=':memory:', read_only=False)
        con.execute("CALL dbgen(sf=0.001);")
        client_connections[client_id] = con

    con = client_connections[client_id]
    df = con.execute("pragma show_tables").fetchdf()
    tables = [[row['name']] for index, row in df.iterrows()]
    for t in tables:
        df = con.execute("pragma table_info('{}')".format(t[0])).fetchdf()
        df['col'] = df['name'].str.cat(df['type'], sep=':')
        col_string = df['col'].str.cat(sep='; ')
        t.append(col_string)
    return tables

if __name__ == '__main__':
    app.run(debug=True)
