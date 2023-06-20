<script lang="ts">

  import { tick, onMount } from "svelte"
  import QueryPlan from "./QueryPlan.svelte"
  import LineageDiagram from "./LineageDiagram.svelte"
  import QueryPicker from "./QueryPicker.svelte"
  import Bug from "./Bug.svelte"
  import * as initial_lineage from "./assets/lineage.json"
  import { lineageData, selectedOpids } from "./stores.ts"
  import {generateUUID} from "./guid"
  const sessionID = generateUUID()

  $lineageData = initial_lineage;

  let msgEl = document.getElementById("msg");
  let queryParams = new URLSearchParams(window.location.search)
  const url = 'http://127.0.0.1:5000';
  let errmsg = null;
  let qplanEl;
  let editorEl;
  let csvEl;
  let newTableName;
  let schemas = [];
  let addedCSVs = [];
  let q = queryParams.get("q") ?? ``;
  let csv = `a,b,c,d,e,f,g
0,0,0,0,a,2,c
1,1,1,0,b,4,d
2,2,0,0,c,6,e
3,3,1,0,d,8,cde
4,4,0,0,abc,10,a
5,0,1,0,cde,12,b
6,1,0,0,a,14,c
7,2,1,0,b,16,abc
8,3,0,0,c,18,c
9,4,1,0,d,20,d`;

  async function getSchema() {
    try {
      const response = await fetch(url+"/schema", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({"client_id": sessionID})
      });
      if (response.ok) {
        errmsg = null;
        const jsonData = await response.json();
        console.log("schema", jsonData);
        return jsonData;
      } else {
        console.error("Error:", response.status);
        errmsg = "Error: " + response.status;
      }
    } catch (error) {
      errmsg = "Error: " + error;
      console.error(errmsg);
    }
  }
  
  async function RegisterCSV(table_name, csv) {
    const data = {'name': table_name, 'csv':csv, "client_id": sessionID};
    try {
      const response = await fetch(url+"/csv", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });

      if (response.ok) {
        errmsg = null;
        schemas = await getSchema();
      } else {
          errmsg = 'Error: ' + response.status;
          console.error(errmsg);
      }
    } catch (error) {
      errmsg = 'Error: ' + error;
      console.log(errmsg);
      console.error(errmsg);
    }
  }

  async function getQueryLineage(q) {
    const data = {'query': q, "client_id" : sessionID};
    try {
      const response = await fetch(url+"/sql", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      if (response.ok) {
        errmsg = null;
        const jsonData = await response.json();
        $lineageData = jsonData;
        console.log("lineageData", lineageData);
        return jsonData; // Return the JSON data to the caller
      } else {
        errmsg = 'Error: ' + response.status;
        console.error(errmsg);
      }
    } catch (error) {
      errmsg = 'Error: ' + error;
      console.error(errmsg);
    }
  }

  async function addTable() {
    if (newTableName) {
      let errorMessage = null;
      if (csv.split("\n").length > 15) {
        errorMessage = "CSV too large for the visualizer to be useful.  Please limit table to 15 rows."
      } else {
        try {
          RegisterCSV(newTableName, csv);
          addedCSVs.push({
            name: newTableName,
            csv
          });
          newTableName = null;
        } catch (e) {
          errorMessage = e;
        }
      }

      addedCSVs = addedCSVs;
      errmsg = "New table needs a name!";
    }
  }

  function onSQLSubmit(){
      getQueryLineage(q);
  }

  function onSelectQuery(query) {
    console.log("selected dropdown", query)
    q = query
  }

  async function init() {
    schemas = await getSchema();
  }

  onMount(() => {
    init();
  })

  function reportBug(comment, email) {
    // TODO: send bug to backend
    //addStat(sessionID, q, JSON.stringify(addedCSVs), errmsg, true, comment, email)
  }

	$: cssVarStyles = `--editor-h:${$lineageData.plan_depth*50+100}px;`;
</script>

<style>
   /* Global styles */
  body {
    line-height: 1.5;
  }

  /* Container styles */
  .container {
    max-width: 960px;
    margin: 0 auto;
    padding: 20px;
  }

  /* Heading styles */
  h1 {
    font-size: 28px;
    margin-bottom: 20px;
  }

  h3 {
    font-size: 20px;
    margin-bottom: 10px;
  }

  /*min-height: var(--editor-h, 30em);*/
  textarea.editor_sql {
    width: 100%;
    min-height: 10em;
    border: 1px solid black;
  }
  textarea.editor_csv {
    width: 100%;
    min-height: 10em;
    border: 1px solid black;
  }
  textarea {
  }
  .viscontainer,.errcontainer {
    margin-top: 3em;
  }
  small {
    font-size: 0.5em;
  }
  a:hover {
    background: var(--bs-highlight-bg);
  }
  .schema {
    padding-left: 0px;
    list-style: none;
  }
  .schema li {
    margin-bottom: .5em;
  }

  .bd-callout {
    padding: 1.25rem;
    margin-top: 1.25rem;
    margin-bottom: 1.25rem;
    background-color: var(--bd-callout-bg, var(--bs-gray-100));
    border-left: 0.25rem solid var(--bd-callout-border, var(--bs-gray-300));
  }

  .bd-callout-danger {
    --bd-callout-bg: rgba(var(--bs-danger-rgb), .075);
    --bd-callout-border: rgba(var(--bs-danger-rgb), .5);
  }

  .schema-list {
    max-height: 200px; /* Adjust the desired height */
    overflow-y: auto;
    border: 1px solid black;
    padding: 5px; /* Add padding for spacing */
  }

</style>

<!--Bug id="modalBug" reportBug={reportBug} /-->


<main class="container-fluid">
 <h1 class="display-4">
   SQLTutor Visualizes Query Execution
  </h1>
  
  <div class="row">
      <h3>About</h3>
      <p>
        <strong>SQLTutor</strong> visualizes each operator in the SQL query plan.
        Click on an operator to visualize its input and output tables, along with their row/column dependencies
        (called <a href="https://dl.acm.org/doi/abs/10.1145/3555041.3589731?casa_token=Vz4Qotq3XOEAAAAA:4YyPliwzUs7idhXMijjgvFVGxr5oVBjMtRuN8GAPJn8c18Y-9opN0Ev1DksDci2Pj7gQu-lQWPc">data provenance</a>).
        You can add new tables using the <mark>CSV</mark> textarea. The CSV should include a header row.
      </p>

      <p style="font-size: smaller;">
        <!--<a target="_blank" href={`https://docs.google.com/forms/d/e/1FAIpQLSeqdk3ZqQms92iaGq5rKV6yUdnhLcRllc8igQPl1KGUwfCEUw/viewform?usp=pp_url&entry.351077705=${encodeURI(q)}&entry.1154671727=${encodeURI(csv)}&entry.1900716371=${encodeURI(errmsg)}`} class="link">Report a bug</a>. -->
        <!--a href="#" class="link" data-bs-toggle="modal" data-bs-target="#modalBug">Report a bug or feature request</a-->.
        <br/>
        <!--Want to help? Contact us!-->
      </p>
  </div> <!-- about section -->

      <div class="row">
          <div class="col">
            <h3>Tables</h3>
            <div class="schema-list">
              <ul class="schema">
                {#each schemas as [name, schema]}
                <li><b>{name}</b>({schema})</li>
                {/each}
              </ul>
            </div> <!--schema-list-->
          </div><!--tables column-->

          <div class="col-md-4">
            <h3>CSV
              <small><input bind:value={newTableName} placeholder="New Table Name" /></small>
            </h3>
            <textarea class="editor_csv" id="csv" bind:this={csvEl} bind:value={csv}></textarea>
            <button class="btn btn-primary" on:click={addTable} style="width:100%;">Add Table</button>
          </div><!--CSV column-->
      </div><!--row-->

<div class="row">
  <h3>
    SQL
    <small><QueryPicker onSelect={onSelectQuery} /></small>
  </h3>
  <textarea class="editor_sql" id="q" bind:this={editorEl} bind:value={q}  style="{cssVarStyles}"></textarea>
  <button class="btn btn-primary" on:click={onSQLSubmit} style="width:100%;">Visualize Query</button>
</div>

{#if $lineageData}
<div class="row viscontainer">
  <div class="row" bind:this={qplanEl}>
    <QueryPlan h={$lineageData.plan_depth * 50 + 100} />
  </div>

</div>

<div class="row viscontainer">
    <LineageDiagram opids={$selectedOpids} />
</div>
{/if}
{#if errmsg}
<div class="row errcontainer">
  <div class="col">
    <div class="bd-callout bd-callout-danger" role="alert">
      <h3>
        Could Not Parse Query
        <small>
          <!--<a target="_blank" href={`https://docs.google.com/forms/d/e/1FAIpQLSeqdk3ZqQms92iaGq5rKV6yUdnhLcRllc8igQPl1KGUwfCEUw/viewform?usp=pp_url&entry.351077705=${encodeURI(q)}&entry.1154671727=${encodeURI(csv)}&entry.1900716371=${encodeURI(errmsg)}`} class="link">report bug</a>-->
          <a href="#" data-bs-toggle="modal" data-bs-target="#modalBug">report bug</a>
        </small>
      </h3>
      <pre>{errmsg}</pre>
    </div>
  </div>
</div>
{/if}

<div class="row footer" style="margin-top: 3em;">
  <div class="col-md-8 offset-md-2 text-center" style="border-top: 1px solid grey;">
    <p style="font-size:smaller;">
      See <a href="https://github.com/haneensa/SQLStepper/tree/sigmod-demo">github repo</a> for code.
      Implemented using a forked version of
      <a href="https://github.com/reallocf/duckdb/tree/lineage_capture">DuckDB</a>
      and table vis from <a href="https://pandastutor.com/">pandastutor</a>.
    </p>
    </div>
  </div>
</main>
