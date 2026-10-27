Here are the three prompt engineering concepts I used: 

# **Few-shot prompting** 

Few-shot prompting means including a small number of examples inside the prompt so the LLM imitates the format and style of those examples. 

**Where I used it** : Each of the four experts reads its own examples together with its own specialized prompt. The examples are stored in the <mark>few_shot_examples</mark> field of each expert and are inserted into that expert’s system prompt through <mark>fll_template</mark> i . The examples show the expert both the structure of the answer and what the answer should contain 

**Why it helped:** Early on, the Orchestrator’s example used a loosely formatted list of function-call strings, and the model copied that format, including its mistakes (missing quotes and misplaced brackets), which caused parsing errors. When I rewrote the examples as a clean JSON array, the model started producing valid JSON. This showed me that examples influence the structure of the output more strongly than written instructions alone. 

# **Decomposition** 

Decomposition means breaking a complex prompt into smaller subprompts, each of which is solved separately, and then combining the results 

**Where I used it:** The Orchestrator expert decomposes the user’s request into a plan of steps for specialized experts. For example, “Does she know JavaScript? If not, add it to his most recent experience” becomes two steps: a Database Read Expert step that checks the skills table, followed by a Database Write Expert step that 

adds the skill. The function <mark>run_orchestrator_plan</mark> executes the steps in order, passes the result of each step to the next one, and then asks the LLM to write one short final reply for the user. 

**Why it helped:** Each expert has one narrow job (generate a SELECT query, generate insert code, or answer from the visible resume), so its output is more reliable than if a single prompt had to understand, query, and modify the database all at once. Passing earlier results to later steps also solved a real problem: the Write step no longer adds a skill that the Read step found to be already present. 



<!-- Start of picture text -->
[orchestrator] generated:<br>[{"role": “Database Read Expert”, “message”: "Does she have JavaScript Listed as a skill?"}, {"role”: "Database Write Expert”, "message": "Add JavaScript as a skill to CSE"}]<br>[orchestrator] executing: role-patabase Read Expert, message-Does she have Javascript Listed as a skill?<br>[orchestrator] executing: role-Database Write Expert, message-Add JavaScript as a skill to CSE<br>[Database write Expert] generated:<br>existing = db.query("SELECT<br>if existing * FROM skills WHERE name = "JavaScript’ AND experienceid = (SELECT experienceid FROM experiences WHERE name = *CSE')")<br>‘outcome = "Element already exists in the skills table.”<br>elsedb. insertRows("skills", [‘experience id’, ‘name’, ‘skill_level'], ["(SELECT experience_id FROM experiences WHERE name = 'CSE')", "JavaScript", 5])<br>‘outcome = "New JavaScript added to the skills table.”<br><!-- End of picture text -->

# **Zero-shot prompting** 

Zero-shot prompting means giving the LLM a task using instructions only, with no examples. 

**Where I used it:** The Content Expert has no few-shot examples. Its prompt only states its role (“answering questions about the resume currently on screen”) and one instruction: “Answer using only the resume content given below as context.” 

**Why it helped:** For simple tasks like answering a question from visible text or summarizing results, clear instructions are enough. Skipping examples keeps the prompt short and avoids the model copying the wording of an example. 

|FH<br>ole<br>40|domain|®£]|_specificinstructions<br>©£1”|few_shotexamples<br>a)|
|---|---|---|---|---|
|fo)<br>800||<br>800|<br> <br>800<br>|<br><br>800<br> <br>|
|11<br>Database Read Expert|SQL query generation for a resume<br>database<br>||Respond<br>with a single valid SQLiteSELECT query only. N...<br>|_@: Howlong<br>dd they work atMSU?-> SELECTpstartd<br> <br>|
|2<br>2<br>Database Write Expert<br><br>|generating Python code thatmodif<br>aresume<br>|ies<br>  database<br>|Respond withexecutablePython only, calling dbinser... <br>|Request: AddPython<br>as asilohis MSU researchexpe.|
|3<br>ContentExpert|answeringquestionsabout theresumecuren<br>|tlyonscre...<br>|Answerusingonlytheresumecontentgivenbelowasc<br><br>|<br>   <br>|
|<br>44<br>Otchestrator|<br>decomposing<br>userrequestsintoaplanofexper|<br>tcalls|<br>Respond<br>withONLYaJSONarray,nomarkdown,noexp...|Request:AddPython<br>asaskilltoCSBasics<br>->{(role’|



