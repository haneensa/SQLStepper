# SQLTutor

<img src="https://github.com/cudbg/sqltutor/raw/main/screenshot.png" style="width:100%"></img>


[Svelte-based SQL visualizer](https://cudbg.github.io/sqltutor).  

Built on top of

* [svelte](https://svelte.dev)
* [SmokedDuck] https://github.com/cudbg/smokedduck) extended duckdb to capture fine-grained lineage
* Table visualizer from [pandastutor](https://pandastutor.com/)

Develop and Run

    npm install .
    npm run dev


# Future Features

* [ ] support for subqueries
* [ ] support for `count(*)`
* [ ] show schemas in interface
* [ ] example list of prewritten queries
* [ ] track usage statistics
* [ ] add new tables

# Specification for lineage data 


```ts
opid: id of operator
Pointers: Array<(outputTupleIdx, inputTupleIdx)>

RowLineage: Array<(sourceTableIndex, Pointers)>

// each element is the list of attribute offsets in the input table's schema
ColIndexes: Array<inputAttrIdx>

// one element for each attribute in the operator's output schema
ColLineage: Array<ColIndexes>

// list of child operator ids
OpLineage: Array<opid>  

// attributes used to filter/join
ExprCols: Array<(sourceTableIndex, ColIndexes)>

Info: {
  str: string // string representation to be displayed
  id: opid
  name: string // operator name
  schema: Array<string>  // attribute names of output schema
}

Tuple: Array<int | string>
Results: {
  columns: Array<string>  // attribute names
  rows: Array<Tuple>
}

Lineage: {
  row: {
    opid: RowLineage
  },
  col: {
    opid: ColLineage
  },
  op: { 
    // "root" is a special opid that stores the root opid in a singleton list
    opid: OpLineage  
  },
  exprs: {
    opid: ExprCols
  },
  info: {
    opid: Info
  },
  results: {
    opid: Results
  },
  qstr: string  // query string
}


```

Setting up the flask server w/ SmokedDuck:
1. Create a new virtual environment `python3 -m venv venvDemo`
2. Access it with `source venvDemo/bin/activate`
3. Install python dependencies with `pip install -r requirements.txt` - after this only SmokedDuck needs to be installed
4. Pull https://github.com/reallocf/duckdb into a new directory and enter it
5. Check out the branch `lineage_capture`
6. Enter the python build directory with `cd tools/pythonpkg`
7. Execute `python setup.py install`
8. Now, from the root of this directory, you can run the backend with `flask --app app run`
