Planning:

O phase 3 do ticket-plan diz p entrar em plan mode, e no prompt do state em planning.py não diz pra entrar.

Se essa parte e a 2 divergem, deveriamos usar essa skill mesmo? Talvez fazer uma headless-ticket-plan skill ajudasse.

Dai fica com menos "nao faz isso na main prompt" e mais "faz isso" direto na skill. 

----

Implementing:

Acho a mesma coisa, deveriamos ter isso mas mais que isso, como é headless, acho que temos que ter uma instrucao de ele pegar contexto. Então acho que cria-se um pattern, talvez devessemos criar um agent que é o "atlassian-context-fetcher" que é o "atlassian-context-fetcher" que vai pegar o contexto do atlassian como jira, confluence, comentarios no ticket, etc. E vai passar pra implementing, assim como ele pode ser usado tb no step do planning.

Só fico me perguntando como nao podemos fazer isso pra ser token efficient e nao repetir essa busca em ambas as partes, poderiamos reaproveitar como esse contexto? sempre pensando em Jira como fonte de verdade e permanencia?

E ai com isso, podemos criar uma skill de headless-ticket-implement que é o "headless-ticket-implement" que vai pegar o contexto do atlassian como jira, confluence, comentarios no ticket, etc. E vai passar pra implementing, assim como ele pode ser usado tb no step do planning. Analogo a como polimos o ticket-plan.

MAs dnv, fico me perguntando se não tem alternativa de fazer isso sem ter q refazer mt do plugin, e sem ficar com as más praticas que temos hoje. Ser interoperante entre o uso do plugin no claude e no dispatcher.

----

Acho que checking_doc e improving_doc sao coisas que deveriam estar no plugin e ser referenciadas no dispatcher. E poderiamos usar das docs na existentes no plugin para isso. Porque ai temos como citar nossos patterns ja existentes de doc no improving_doc por exemplo. Pq ele não sabe como funciona (e se vc for ver, é nosso skill mais complexo). Tanto que o retry dela é feito quando alguem fez comentario inline no doc e o modelo precisa extrair isso e enfim... 

(Also aqui temos que pensar oonde podemos guardar o output do design-pattern agent por exempplo para nao ter que triggar dnv na hora do improving-doc).







