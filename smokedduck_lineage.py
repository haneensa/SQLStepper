#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import numpy as np
import json
import re

def runQuery(con, q, qname):
    con.execute('PRAGMA threads=1')
    con.execute("PRAGMA enable_lineage ;")
    con.execute("PRAGMA enable_intermediate_tables;")
    df = con.execute(q).fetchdf() 
    con.execute("PRAGMA disable_intermediate_tables;")
    con.execute("PRAGMA disable_lineage;")
    metadata_df = con.execute("SELECT query_id, plan FROM duckdb_queries_list() WHERE query=?", [q]).fetchdf()
    c = len(metadata_df)
    print(metadata_df)
    qid = metadata_df['query_id'][c-1]
    plan_text = metadata_df['plan'][c-1]
    plan_json = json.loads(plan_text)
    
    return df, qid, plan_json


def OperatorName(name):
    return "_".join(name.split("_")[:-1])
    
def getColumnLevelLineage(qid : int, plan : dict, parent : dict):
    """
    return operator level column lineage:
    "original": str, # plan["extra"]
    "table_name":  str, # table_name
    "alias":  [str], # [alias(col) for each col in current operator]
    "column_ref": [int] # [indexFromChild(col) for each col in current operator]
    """
    if "extra" not in plan:
        return {}
    
    extra = plan["extra"].split("[INFOSEPARATOR]")
    results = {"original": extra}
    op_name = OperatorName(plan['name'])    
    
    print(op_name, parent["name"])
    if len(plan["children"]) > 0:
        results["table_name"] = plan['children'][0]["name"]

    if op_name == "SEQ_SCAN":
        # Schema: table_name\nINFOSEPARATOR\ncolname_i for i in projection_list\nINFOSEPARATOR\nFilters: ..
        results["table_name"] = extra[0].strip()
        results["str"] += "Input: {}".format(results['table_name'])
        if len(extra) > 1:
            cols =  extra[1].strip().split("\n")
            results["alias"] = [x.split("#DEL#")[0] for x in cols]
            results["col_ref"] = [x.split("#DEL#")[1].split(',') for x in cols]
            results["col_ref"] = [[int(i) for i in inner_lst] for inner_lst in results["col_ref"]]
            results["str"] += " | Cols: [{}].".format(', '.join(results["alias"]))
        if len(extra) > 2:
            results["filter_push"] = 1
            results["str"] += " | {}".format(extra_info[2].strip())
    elif op_name == "DELIM_SCAN":
        #join["delim_data"] = [agg, left]
        results = dict(plan["delim_data"][0]["column_lineage"])
        results["str"] = "Read output of " + plan["delim_data"][0]["name"]
    elif op_name in ["FILTER", "ORDER_BY", "LIMIT"]:
        # TODO: filter does have projection push down. handle it
        if "alias" in plan["children"][0]["column_lineage"]:
            results["alias"] = plan["children"][0]["column_lineage"]["alias"]
            results["col_ref"] = plan["children"][0]["column_lineage"]["col_ref"]
        if op_name == "FILTER":
            results["str"] = plan["extra_info"]
        elif op_name == "ORDER_BY":
            # e.g. '#0 ASC\n#1 ASC\n#2 ASC'
            col_order = plan["extra_info"].split('\n')
            col_dir = [(int(col.split(' ')[0][1:]), col.split()[-1]) for col in col_order if col]
            col_dir_alias = ["{} {}".format(results["alias"][x[0]], x[1]) for x in col_dir]
            results["str"] +=  "Order By: {}".format(', '.join(col_dir_alias))
        elif op_name == "LIMIT":
            # TODO: extend operator to return limit and offset values
            print(extra_info)
            results["str"] += "LIMIT"
    elif op_name == "PROJECTION":
        # Schema: hasFunction\nINFOSEPARATOR\nalias_i.col_1,col_2,..,col_n.name_i for i in projection_list
        cols =  extra[1].strip().split("\n")
        results["alias"] = [x.split("#DEL#")[0] for x in cols]
        results["col_ref"] = [x.split("#DEL#")[1].split(',') for x in cols]
        results["col_ref"] = [[int(i) for i in inner_lst if i.isdigit()] for inner_lst in results["col_ref"]]

        # if we can propagate alias from children, then do that
        if "alias" in plan["children"][0]["column_lineage"]:
            child_col_lineage = plan["children"][0]["column_lineage"]["alias"]
            results["alias"] = [ child_col_lineage[int(x[1:])]  if (x.startswith("#") and len(child_col_lineage) > int(x[1:])) else x for x in results["alias"] ]
        results["str"] += " Cols: [{}].".format(', '.join(results["alias"]))

    elif op_name in ["HASH_GROUP_BY", "PERFECT_HASH_GROUP_BY"]:
        aggs = extra[0].strip().split("\n")

        if len(plan["children"]) > 0:
            child_col_lineage = plan["children"][0]["column_lineage"]["alias"]
        elif OperatorName(parent["name"]) == "DELIM_JOIN":
            child_col_lineage = plan["delim_children"]["column_lineage"]["alias"]
            results["str"] += " Duplicate eliminate for correlated subquery eval | "
        else:
            gb_keys = [x for x in aggs if x.startswith("#")]
            aggs_cols = [x for x in aggs if not x.startswith("#")]
        
        gb_keys = [child_col_lineage[int(x[1:])] for x in aggs if x.startswith("#")]
        aggs_cols = [x for x in aggs if not x.startswith("#")]

        results["alias"] = gb_keys + aggs_cols
        results["col_ref"] = [[i] for i in range(len(gb_keys))]
        results["col_ref"] += [[int(i) for i in re.findall(r"#(\d+)", x)] for x in aggs_cols]
        results["str"] += "Key: [{}].".format(', '.join(gb_keys))
        results["str"] += ", Aggs: [{}].".format(', '.join(aggs_cols))
    elif op_name == "SIMPLE_AGGREGATE":
        cols = extra[0].strip().split("\n")
        results["alias"] = [x.split("#DEL#")[0] for x in cols]
        results["col_ref"] = [x.split("#DEL#")[1].split(',') for x in cols]
        results["col_ref"] = [[int(i) for i in inner_lst if i.isdigit()] for inner_lst in results["col_ref"]]
    elif op_name == "DELIM_JOIN":
        results = dict(plan["children"][2]["column_lineage"])
    elif op_name in ["CROSS_PRODUCT", "INDEX_JOIN", "PIECEWISE_MERGE_JOIN", "NESTED_LOOP_JOIN", "BLOCKWISE_NL_JOIN", "DELIM_JOIN"]:
        results["table_name"] += "+" + plan['children'][1]["name"]
        join_cond = results["original"][0].strip()
        results["str"] += join_cond
        rchild_col_lineage = plan["children"][1]["column_lineage"]
        lchild_col_lineage = plan["children"][0]["column_lineage"]
        if "alias" in rchild_col_lineage:
            right_alias = rchild_col_lineage["alias"]
        if "alias" in lchild_col_lineage:
            left_alias = lchild_col_lineage["alias"]
        results["alias"] = list(left_alias)
        results["alias"] += list(right_alias)
        results["col_ref"] = [[i] for i in range(len(results["alias"]))] 
    elif op_name in ["HASH_JOIN"]:
        results["table_name"] += "+" + plan['children'][1]["name"]
        results["alias"] = []
        right_projection = extra[1].strip()
        if OperatorName(parent["name"]) == "DELIM_JOIN" and "delim_left" in plan:
            results["str"] += " Delim Join | "
            left = plan["delim_left"]
        else:
            left = plan["children"][0]
        lchild_col_lineage = left["column_lineage"]
        print(left['name'], lchild_col_lineage)
        rchild_col_lineage = plan["children"][1]["column_lineage"]
        print("right_projection: ", right_projection, len(right_projection), rchild_col_lineage)
        right_alias, left_alias = [], []
        if "alias" in rchild_col_lineage:
            right_alias = rchild_col_lineage["alias"]
        if "alias" in lchild_col_lineage:
            left_alias = lchild_col_lineage["alias"]
        results["col_ref_left"] = [[i] for i in range(len(left_alias))] 

        results["alias"] += list(left_alias)
        
        results["col_ref_right"] = []

        join_cond = results["original"][0].strip()
        results["str"] += join_cond
        if join_cond[:4] in ["SEMI","ANTI"]:
            print('semi join, skip right side')
        elif join_cond[:4] == "MARK":
            results["alias"] += ["IN"]
        elif len(right_projection) > 0:
            for i in right_projection.split('\n'):
                col = right_alias[int(i[1:])]
                results["col_ref_right"] += [[col]]
                results["alias"] += [col]
        else:
            print("right_alias", right_alias)
            results["col_ref_right"] = [[i] for i in range(len(right_alias))]
            results["alias"] += list(right_alias)
        
        results["col_ref"] = [[i] for i in range(len(results["alias"]))]

    return results
    
def getLineagePerOperatortoPlan(con, qid, plan):
    # traverse the query plan, and 
    op_name = plan['name']
    l_name = "LINEAGE_{}_{}_0".format(qid, op_name)        
    ## for now, just merge data using python.
    ## TODO: enable querying logical operator lineage
    op_name = OperatorName(op_name)    
    if op_name in ["SEQ_SCAN", "ORDER_BY", "FILTER", "LIMIT"]:
        extra = plan["extra"].split("[INFOSEPARATOR]")
        if op_name == "SEQ_SCAN" and len(extra) < 2:
            # one to one mapping, no need to persist
            return []
    
    # skip
    if op_name in ["PROJECTION"]:
        return []

    op_lineage = con.execute("select * from {}".format(l_name)).fetchdf()

    return op_lineage
    
def getIntermediates(con, qid, plan):
    # start from leaf node, get base table, then merge and propagate intermediate table 
    name = plan['name']
    l_name = "LINEAGE_{}_{}_100".format(qid, name)        
    op_name = OperatorName(name)    
    base_table = []
    if op_name == "SEQ_SCAN":
        table_name = plan["column_lineage"]["table_name"]
        base_table = con.execute("SELECT * FROM {}".format(table_name)).fetchdf()
        # TODO: check the case where input == output and avoid duplicating data
    if op_name == "ORDER_BY":
        input_df = plan["children"][0]["output"]
        if "lineage" not in plan:
            return pd.DataFrame(), base_table
        intermediate = pd.merge(plan["lineage"], input_df, how='inner', left_on='in_index',  right_index=True, ).sort_values(by="out_index").drop(columns=["out_index", "in_index"])
    else:
        intermediate = con.execute("select * from {}".format(l_name)).fetchdf()
    return intermediate, base_table

# column: operator_id : operator_id_column_lineage for each operator in plan
# row: operator_id : operator_id_row_lineage for each operator in plan

# operator_id_row_lineage: 
# [ [oid, iid] for each tuple ]

# operator_id_column_lineage: array[array] 
# where the index is the index of the dst table
# and the inner array has a list of src columns that map to the dst
def getRowLineage(qid, plan, depth, lineage_json):
    """
    {opid: Array[ Array[srcidx, Array[oid, iid]] ] 
    """ 
    if "lineage" not in plan:
        return {}
    if len(plan['lineage']) == 0:
        return {}
  
    lineage_out = {}
    lineage = []
    op_name = OperatorName(plan["name"])    
    lineage_relation = plan["lineage"]
    """
    lineage_relation = lineage_relation.iloc[:limit]
    s = 0
    e = len(lineage_relation)
    num_rows = min(limit, len(lineage_relation))
    random_values = np.random.choice(np.arange(s, e), size=num_rows, replace=False)
    random_values = np.sort(random_values)
    lineage_relation = lineage_relation.iloc[random_values]
    """
    if op_name in ["HASH_JOIN", "CROSS_PRODUCT", "INDEX_JOIN", "PIECEWISE_MERGE_JOIN", "NESTED_LOOP_JOIN", "BLOCKWISE_NL_JOIN"]:
        limit = 200
        if len(lineage_relation) > limit:
            lineage_json["info"][plan["name"]]["str"] += ". {} sampled lineage edges out of {}".format(limit, len(lineage_relation))
            #lineage_relation = lineage_relation.iloc[:limit]
            s = 0
            e = len(lineage_relation)
            num_rows = min(limit, len(lineage_relation))
            random_values = np.random.choice(np.arange(s, e), size=num_rows, replace=False)
            random_values = np.sort(random_values)
            lineage_relation = lineage_relation.iloc[random_values]
        lineage_relation['lhs_index'] = lineage_relation['lhs_index'].fillna(-1)
        lineage_relation['rhs_index'] = lineage_relation['rhs_index'].fillna(-1)
        lineage_lhs = [[int(row['out_index']), int(row['lhs_index'])] for index, row in lineage_relation.iterrows()]
        lineage_rhs = [[int(row['out_index']), int(row['rhs_index'])] for index, row in lineage_relation.iterrows()]
        lineage_out[plan["name"]] = [[0, lineage_lhs]]
        lineage_out[plan["name"]].append([1, lineage_rhs])
    else:
        if (op_name == "SEQ_SCAN" and "filter_push" not in plan["column_lineage"]) or len(plan["lineage"]) == 0:
            return {}
        else:
            lineage = [[int(row['out_index']), int(row['in_index'])] for index, row in lineage_relation.iterrows()]
            lineage_out[plan["name"]] = [[0, lineage]]
    return lineage_out
        
def GetDisplayName(plan):
    opname = OperatorName(plan["name"])
    if opname == "HASH_JOIN":
        return "HJ"
    elif opname == "DELIM_JOIN":
        return "delim join"
    elif opname == "SEQ_SCAN":
        return plan["column_lineage"]["table_name"]
    elif opname in ["HASH_GROUP_BY", "PERFECT_HASH_GROUP_BY"]:
        return "GB"
    elif opname == "PIECEWISE_MERGE_JOIN":
        return "MJ"
    elif opname == "SIMPLE_AGGREGATE":
        return "agg"
    elif opname == "ORDER_BY":
        return "order by"
    else:
        return opname.lower()
def getInfo(qid, plan, depth, lineage_json):
    """
    return info : dict(opid : opinfo)

    opinfo:
        "name": str, # operator name
        "str": str, # operator describtion
        "schema":  [str], # [alias(col) for each col in current operator]
        "id": str, # operator unique id
        "depth": int, # operator depth within the query plan
        "table_name"? : str, # if "name" is SEQ_SCAN,
        "input" : [int], # input cardinality
        "output" : int,  # output cardinality

    "col": dict(opid : column_ref)
        "column_ref": [int] # [indexFromChild(col) for each col in current operator]

    results: dict(opid : input)
        "input": [], # row input data to this operator
    """
    info = {}
    opid = plan['name']
    op_name = OperatorName(opid)    
    info["str"] = plan["column_lineage"]["str"]

    info["name"] = op_name

    if op_name == "SEQ_SCAN":
        info["table_name"] = plan["column_lineage"]["table_name"]
    
    if 'column_lineage' in plan and "alias" in plan['column_lineage']:
        info["schema"] = plan['column_lineage']["alias"]

    if "delim_children" in plan:
        info["delim_children"] = plan["delim_children"]["name"]
    #info["input"] = 
    #info["output"] = 

    info["id"] = opid
    info["display_name"] = GetDisplayName(plan)
    info["depth"] = depth
    opid_number = opid.rsplit("_", 1)[-1]
    info["id_number"] = opid_number
    
    return {opid : info}
     
def getResults(qid, plan, depth, lineage_json):
    res = {}
    if "input" in plan:
        base = plan["input"]
        """
        #base = base.iloc[:limit]
        s = 0
        e = len(base)
        num_rows = mi(limit, len(base))
        random_values = np.random.choice(np.arange(s, e), size=num_rows, replace=False)
        random_values = np.sort(random_values)
        base = base.iloc[random_values]
        """
        col_names = list(base.columns)
        # Convert datetime columns to strings
        for col in list(base.columns):
            base[col] = base[col].astype(str)
            
        base_rows = [row.values.tolist() for index, row in base.iterrows()]
        res[plan["name"]+"input"] = {"rows": base_rows, "columns": col_names, "cardinality" : len(base)}
    
    if "output" in plan:
        base = plan["output"]
        """
        #base = base.iloc[:limit]
        s = 0
        e = len(base)
        num_rows = min(limit, len(base))
        random_values = np.random.choice(np.arange(s, e), size=num_rows, replace=False)
        random_values = np.sort(random_values)
        base = base.iloc[random_values]
        """
        col_names = list(base.columns)
         
        # Convert datetime columns to strings
        for col in list(base.columns):
            base[col] = base[col].astype(str)
            
        base_rows = [row.values.tolist() for index, row in base.iterrows()]
        if "alias" in plan['column_lineage']:
            alias = plan['column_lineage']["alias"]
        else:
            alias = col_names
        
        res[plan["name"]] = {"rows": base_rows, "columns": alias, "cardinality" : len(base)}
        
    return res

def serializeLineage(qid, plan, depth=0, lineage_json={}):
     # traverse the query plan, and 
    if depth == 0:
        # setup query level summary
        lineage_json["exprs"] = {}
        lineage_json["plan_depth"] = 0
        
        lineage_json["op"] = {"root" : [plan["children"][0]["name"]]}
        # "col": {"233": [[0, 1], [2], [3]], "236": [[0], [4], [3]]}, 
        lineage_json["col"] = {}
        # "exprs": {"280": [[0, [0]], [1, [1]]]},
        lineage_json["exprs"] = {}
        
        # intermediate tables
        lineage_json["results"] = {}
        # setup info:
        lineage_json["info"] = {}
        
        lineage_json["row"] = {}
        lineage_json["expr"] = {}
    else:

        lineage_json["op"][plan["name"]] = [c["name"] for c in plan['children']]
        info = getInfo(qid, plan, depth, lineage_json)
        lineage_json["info"].update(info)

        res = getResults(qid, plan, depth, lineage_json)
        lineage_json["results"].update(res)
        
        if "col_ref" in plan["column_lineage"]:
            col_lineage = plan["column_lineage"]
            if "col_ref_left" in col_lineage:
                lineage_json["expr"][plan['name']] = {0 : col_lineage["col_ref_left"], 1: col_lineage["col_ref_right"]}

            col_ref = col_lineage["col_ref"]
            lineage_json["col"][plan['name']] = col_ref
            print(plan["name"], lineage_json["col"][plan["name"]])

        lineage_out = getRowLineage(qid, plan, depth, lineage_json)
        lineage_json["row"].update(lineage_out)

    lineage_json["plan_depth"] = max(depth, lineage_json["plan_depth"])
    
    depth += 1    
    
    for idx, c in enumerate(plan['children']):  
        serializeLineage(qid, c, depth, lineage_json)

    return lineage_json

def extractMetadata(con, qid, plan, depth=0):
    depth += 1    
    for idx, c in enumerate(plan['children']):  
        # get lineage for operator
        # return empty for 1:1 mappings or no lineage for operator
        # supported operators: ["SEQ_SCAN", "ORDER_BY", "FILTER", "LIMIT",
        #                       "HASH_GROUP_BY", "PERFECT_HASH_GROUP_BY", "HASH_JOIN",
        #                       "CROSS_PRODUCT", "INDEX_JOIN", "PIECEWISE_MERGE_JOIN", 
        #                       "NESTED_LOOP_JOIN", "BLOCKWISE_NL_JOIN"]
        lineage = getLineagePerOperatortoPlan(con, qid, c)
        if len(lineage):
            # only persist if
            c["lineage"] = lineage
        
        extractMetadata(con, qid, c, depth)

        c["column_lineage"] = getColumnLevelLineage(qid, c, plan)
        print("column lineage for {} ".format(c["name"]), c["column_lineage"])
        
        intermediate, base_table = getIntermediates(con, qid, c)
        c["output"] = intermediate
        if len(base_table) > 0:
            c["input"] = base_table

        print("Intermediates for {} ".format(c['name']), c["output"])
            

## Done - Add leaf node to indicate scan from base table since SEQ_SCAN can have filter pushed down
## add projection list for operators that have projection push down ("e.g. scan, join, filter")

def serializeRelation(base):
    col_names = list(base.columns)
    # Convert datetime columns to strings
    for col in list(base.columns):
        base[col] = base[col].astype(str)

    base_rows = [row.values.tolist() for index, row in base.iterrows()]
    return base_rows, col_names

def debug(plan):
    print("*****debug", plan["name"])
    if plan["name"] == "HASH_JOIN_26":
        print("extract metadata ***", plan["name"], plan["column_lineage"])
    for idx, c in enumerate(plan['children']):  
        debug(c)

def UpdateDelimScans(join, agg, left):
    if OperatorName(join["name"]) == "DELIM_SCAN":
        print("delim scan", join, agg, left)
        join["delim_data"] = [agg, left]

    for c in join["children"]:
        UpdateDelimScans(c, agg, left)

def addDelimJoinAnnotation(plan):
    if OperatorName(plan["name"]) == "DELIM_JOIN":
        print("*****", len(plan["children"]))
        #print("delim join childrens: ", plan["children"][0]["name"], plan["children"][1]["name"], plan["children"][2]["name"])
        # left is the input to the hash aggregate for duplicate elimination
        # left -> SINK (DELIM JOIN distinct (agg))
        join = plan["children"][-2]
        agg = plan["children"][-1]
        if len(plan["children"]) > 2:
            left = plan["children"][0]
        else:
            left = plan["children"][0]
        
        agg["delim_children"] = left
        
        #join["children"][0] = left
        join["delim_left"] = left
        plan["children"] = [left, agg, join]
        # for any delim scan in delim join, the input to them is the output of agg
        UpdateDelimScans(join, agg, left)
        # make the parent of this operator this operator
    for c in plan["children"]:
        addDelimJoinAnnotation(c)

def process(con, q, qname):
    print("**********{}**********".format(qname))
    print(q)
    df, qid, plan = runQuery(con, q, qname)
    print("\noutput:\n", df)
    print("\nPlan:\n", plan)
    lineage_json = {}

    addDelimJoinAnnotation(plan)

    extractMetadata(con, qid, plan, 0)
    # get the column names for root operator from the final result
    plan["children"][0]["column_lineage"]["alias"] = list(df.columns)
    
    lineage_json = serializeLineage(qid, plan, 0, {})
    lineage_json["qstr"] = q

    #print("\nlineage json:\n", lineage_json)

    with open('{}.json'.format(qname), 'w') as outfile:
        json.dump(lineage_json, outfile)

# delim: 2, 17, 20, 21
# TODO: get join keys column reference
# TODO: annotate delim join to make it explainable
# TODO: when delim join, its hash join child columns has extra attribute
# TODO: delim join hash join projection is empty
# TODO: delim join connect hash join delim scan with group by
# TODO: replace '#x' with the column name they are referencing applicable to: order by, group by, projections functions
# q9 UI is slow
# TODO: add limit column annotations
