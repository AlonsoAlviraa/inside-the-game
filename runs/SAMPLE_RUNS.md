# Real Azure end-to-end runs (2026-10-19, gpt-4.1-mini, MAF orchestrator, seed 7)

## Run 1: fan · Spanish · favourite club Harbour City Mariners · speed 20 (~6 min)
```
ticks 1980 batches 21
{
 "input_tokens": 20410,
 "output_tokens": 4573,
 "calls": 43,
 "usd": 0.01548,
 "by_agent": {
  "interpret": {
   "calls": 6,
   "input": 5813,
   "output": 437,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 7
  },
  "explain": {
   "calls": 18,
   "input": 6817,
   "output": 2428,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 0
  },
  "personalise": {
   "calls": 19,
   "input": 7780,
   "output": 1708,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 0
  }
 }
}
fact-check rejections 1 llm states {'azure': 43}
{'ingest': (0, 1), 'salience': (0, 0), 'interpret': (607, 2850), 'explain': (1975, 7857), 'render': (0, 0), 'personalise': (2657, 9154)}
anomalies 0 dups 0
  6' [phase       ] p4 explain-llm+personalised   Cambio de fase | ¡Esto se ha puesto intenso con Ironridge Rovers dominando desde el minuto 6, pero Harbour City Mariners pueden sorprender!
  6' [insight     ] p3 interpret-llm              Tactical read | Ironridge Rovers dominate control and passing accuracy in this chaotic phase, creating slightly more threat despite the early 0-0 scoreline.
  7' [stat        ] p4 explain-llm+personalised   Pase rompelineas | ¡Harbour City Mariners no paran de presionar con pases veloces que meten miedo!
  6' [stat        ] p4 explain-llm+personalised   Pase rompelineas | Kian Juniper lanzó un pase rápido de 6.5m a 58.5 km/h, aumentando la amenaza en 0.06.
  6' [chance      ] p4 explain-llm+personalised   Oportunidad · Kian Juniper | Kian Juniper disparó a 106.5 km/h desde 8m con 0.093 de amenaza esperada, pero falló el tiro.
 11' [chance      ] p5 explain-llm+personalised   Oportunidad · Hugo Northam | ¡Hugo Northam casi marca con un disparo potente para Harbour City Mariners en el minuto 11!
 11' [stat        ] p5 explain-llm                Line-breaking pass | Also at minute 11, Kian Juniper's 30.2m pass added 0.1 xT for Harbour City Mariners, advancing play during a chaotic phase and contributing positively to his 0.16 player xT.
 16' [phase       ] p4 explain-llm                Phase shift | At minute 16, the game shifted from siege to chaos phase with Ironridge Rovers holding stronger control (0.654) than Harbour City Mariners (0.396), indicating a dynamic and unpredictable period.
 21' [insight     ] p3 interpret-llm+personalised Lectura táctica | ¡Ironridge Rovers están dominando el control y el impulso, pero Harbour City Mariners no se rinden!
 26' [phase       ] p4 explain-llm+personalised   Cambio de fase | ¡Vamos Harbour City Mariners, no dejes que Ironridge Rovers te quiten el control!
 23' [chance      ] p3 explain-llm+personalised   Oportunidad · Hugo Northam | Hugo Northam intentó un disparo rápido a 90 km/h desde 10.8 metros, pero no acertó.
 22' [chance      ] p2 explain-llm+personalised   Oportunidad · Cyro Juniper | Cyro Juniper lanzó un potente disparo a 114.1 km/h desde 19.8 metros, pero fue detenido.
 26' [chance      ] p5 explain-llm+personalised   Oportunidad · Arlo Underhill | ¡Arlo Underhill casi marca para Ironridge Rovers con un disparo potente desde muy cerca!
 26' [stat        ] p4 explain-llm                Line-breaking pass | Bento Calder's long 40-meter pass at 76.6 km/h added 0.08 expected threat, advancing Ironridge Rovers' control and creating potential scoring opportunities.
 27' [chance      ] p3 explain-llm                Chance · Zeno Northam | Zeno Northam's shot from 12.8 meters went off target, missing a chance to break the deadlock and keeping the score level at 0-0.
 36' [phase       ] p5 explain-llm+personalised   Cambio de fase | ¡Vamos Harbour City Mariners! Dominan el partido con mucha presión, ¡a por el gol!
 36' [insight     ] p3 interpret-llm+personalised Análisis táctico | Harbour City Mariners mantienen un índice de control alto de 0.695, con gran precisión en pases y volumen de disparos para superar la defensa de Ironridge Rovers.
 35' [chance      ] p4 explain-llm+personalised   Oportunidad · Hugo Northam | En el minuto 35, Hugo Northam dispara a 88.9 km/h desde 13.6m, pero falla el gol que podría romper el empate.
 37' [goal        ] p5 explain-llm+personalised   GOAL · HCM 0-1 IRR | ¡No puede ser! Ironridge Rovers marca con eficacia mientras Harbour City Mariners dominan sin gol.
 42' [stat        ] p4 explain-llm+personalised   Pase rompelineas | ¡Ironridge Rovers controla el partido con un pase rápido que mantiene el 1-0 contra Harbour City Mariners!
 43' [stat        ] p4 explain-llm+personalised   Pase rompelineas | Joss Calder de Harbour City Mariners intenta presionar con un pase corto de 3.9m para remontar el 0-1.
 48' [period      ] p5 explain-llm+personalised   HCM 0-1 IRR | ¡Vamos Harbour City Mariners, aún podemos remontar este partido! No dejéis que Ironridge Rovers se relajen.
 48' [phase       ] p4 explain-llm                Phase shift | At minute 48, the game shifted from chaos to control favoring Ironridge Rovers, who hold a higher control index (0.64) than Harbour City Mariners (0.545), indicating stronger possession and organization.
 51' [insight     ] p3 interpret-llm+personalised Tactical read | ¡Harbour City Mariners dominan el juego y Kian Juniper está creando peligro constante!
 48' [card        ] p3 explain-llm                Yellow card | At minute 48, Zeno Northam of Ironridge Rovers received a yellow card during a chaotic phase, potentially impacting his aggression and the team's dynamics while leading 1-0 against HCM.
 62' [stat        ] p4 explain-llm+personalised   Pase rompelineas | ¡Ironridge Rovers mantiene el control con un pase clave de Fenn Thornby a 55 km/h que aumenta la amenaza!
 68' [stat        ] p4 explain-llm+personalised   Pase rompedor | ¡Harbour City Mariners deben reaccionar rápido tras el pase peligroso de Ilan Elmsworth!
 71' [stat        ] p5 explain-llm+personalised   Pase rompedor | Gael Greywick intenta reducir la desventaja con un pase de 23.7m que añade 0.09 de amenaza.
 71' [phase       ] p4 explain-llm+personalised   Cambio de fase | Ironridge Rovers recupera el control con un índice de control de 0.594 frente a 0.572 de Harbour City Mariners.
 74' [stat        ] p4 explain-llm+personalised   Pase rompedor | ¡Gael Greywick lanza un pase rápido de 6.3m para intentar darle la vuelta al partido!
 72' [card        ] p3 explain-llm+personalised   Tarjeta amarilla | A los 72 minutos, Hale Ingleby de Ironridge Rovers recibió una amarilla, lo que podría cambiar su defensa mientras mantienen el 1-0.
 77' [stat        ] p5 explain-llm+personalised   Pase rompedor | ¡Gael Greywick lanza un pase rápido de 9.1m que puede cambiar el partido para Harbour City Mariners!
 81' [phase       ] p4 explain-llm+personalised   Cambio de fase | Al minuto 81, Harbour City Mariners domina con un índice de control de 0.683 frente a 0.496 de Ironridge Rovers, aumentando sus oportunidades.
 81' [insight     ] p3 interpret-llm+personalised Lectura táctica | El partido sigue caótico con Harbour City Mariners ligeramente por delante en control, pero Ironridge Rovers mantiene la ventaja.
 85' [stat        ] p5 explain-llm+personalised   Pase que rompe líneas | ¡Joss Calder lanzó un pase rápido de 25 metros que pudo cambiar el partido para Harbour City Mariners!
 84' [chance      ] p4 explain-llm+personalised   Oportunidad · Nilo Thornby | Nilo Thornby intentó un disparo lejano de 33.5 metros a 90.7 km/h, pero fue bloqueado en el minuto 84.
 85' [chance      ] p4 explain-llm+personalised   Oportunidad · Kian Juniper | Kian Juniper disparó fuera en el minuto 85 desde 34.8 metros a 109.1 km/h, mostrando gran agresividad ofensiva.
 91' [phase       ] p4 explain-llm+personalised   Cambio de fase | ¡Harbour City Mariners luchan hasta el final pero Ironridge Rovers domina en el último minuto!
 91' [chance      ] p3 explain-llm+personalised   Oportunidad · Zeno Northam | Zeno Northam disparó a 94 km/h desde 14 metros, pero el portero mantuvo el 1-0 para Ironridge.
 89' [chance      ] p4 explain-llm+personalised   Oportunidad · Oren Birchall | Oren Birchall intentó un disparo de 27 metros a 106 km/h, pero fue bloqueado y Harbour City Mariners siguen perdiendo.
 95' [period      ] p5 explain-llm+personalised   HCM 0-1 IRR | ¡Ironridge Rovers aguantan el 1-0 en el último suspiro, Harbour City Mariners deben apretar más!
 93' [substitution] p4 explain-llm+personalised   Sustitución | En el minuto 93, Harbour City Mariners cambian a Quin Elmsworth por Dario Vance para intentar remontar el 0-1.
 95' [period      ] p5 explain-llm+personalised   HCM 0-1 IRR | ¡Los Ironridge Rovers ganaron sin brillo, pero Harbour City Mariners lucharon hasta el final!
REJECT 6 personalise 1
REJECT 66 interpret "rejected ['0.55', '0.58']"
```

## Run 2: analyst · English · speed 60 (after fixes: single full-time card, MCP facts)
```
ticks 1980 batches 21
{
 "input_tokens": 12383,
 "output_tokens": 2892,
 "calls": 24,
 "usd": 0.00958,
 "by_agent": {
  "interpret": {
   "calls": 6,
   "input": 5718,
   "output": 460,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 7
  },
  "explain": {
   "calls": 18,
   "input": 6665,
   "output": 2432,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 0
  }
 }
}
fact-check rejections 0 llm states {'azure': 24}
{'ingest': (0, 3), 'salience': (0, 0), 'interpret': (819, 7266), 'explain': (2669, 9807), 'render': (0, 0), 'personalise': (0, 0)}
anomalies 0 dups 0
  6' [phase       ] p4 explain-llm                Phase shift | At minute 6, the game shifted from kick-off to chaos with Ironridge Rovers dominating control at 0.816, indicating a high-intensity phase that could lead to scoring opportunities.
  6' [insight     ] p3 interpret-llm              Tactical read | Ironridge Rovers dominate control index at 0.816 with high pass accuracy (91%) and volume, while the match remains chaotic and goalless at minute 6.
  4' [stat        ] p3 explain-llm                Line-breaking pass | At minute 4, Bento Calder of Ironridge Rovers made a fast 3-meter pass adding 0.06 xT, helping maintain pressure during a chaotic phase with the score still 0-0.
  7' [stat        ] p4 explain-llm                Line-breaking pass | Ivo Underhill made a quick 9.6m pass at 48.8 km/h adding 0.07 expected threat, helping Harbour City Mariners maintain pressure during a scoreless siege at minute 7.
  6' [stat        ] p4 explain-llm                Line-breaking pass | Kian Juniper's fast 6.5m pass at 58.5 km/h increased expected threat by 0.06, contributing to Harbour City Mariners' attacking build-up early in the match.
  6' [chance      ] p4 explain-llm                Chance · Kian Juniper | Kian Juniper took an off-target shot from 8m at 106.5 km/h with 0.093 xG, showing attacking intent despite no goal, keeping pressure on the opposition at minute 6.
 11' [chance      ] p5 explain-llm                Chance · Hugo Northam | At minute 11, Hugo Northam of Harbour City Mariners took a close-range shot with high speed, which was saved, maintaining the 0-0 score and reflecting a high-pressure chaos phase with significant scoring opportunity.
 11' [stat        ] p5 explain-llm                Line-breaking pass | Also at minute 11, Kian Juniper made a long, fast 30.2m pass adding 0.1 expected threat, helping Harbour City Mariners build pressure during the chaotic phase despite no immediate score change.
 16' [phase       ] p4 explain-llm                Phase shift | By minute 16, the game shifted from siege to chaos phase with Ironridge Rovers holding higher control (0.654) than Harbour City Mariners (0.396), indicating increased unpredictability and contest for possession.
 21' [insight     ] p3 interpret-llm              Tactical read | Despite Harbour City Mariners' control phase, Ironridge Rovers show higher control index (0.649 vs 0.515) and chaos (0.633), with Kian Juniper leading threat for Mariners.
 26' [phase       ] p4 explain-llm                Phase shift | At minute 26, Ironridge Rovers slightly increased their control index to 0.626, surpassing Harbour City Mariners at 0.609, signaling a subtle shift in momentum during a moderately chaotic phase (0.567 chaos index).
 23' [chance      ] p3 explain-llm                Chance · Hugo Northam | At minute 23, Hugo Northam of Harbour City Mariners took a fast 90 km/h shot from 10.8 meters, but it went off target, missing a chance to break the 0-0 deadlock despite a modest expected goal value of 0.058.
 22' [chance      ] p2 explain-llm                Chance · Cyro Juniper | At minute 22, Cyro Juniper of Ironridge Rovers fired a 114.1 km/h shot from 19.8 meters, which was saved, maintaining the 0-0 scoreline and reflecting a low but real scoring opportunity (xG 0.035).
 26' [chance      ] p5 explain-llm                Chance · Arlo Underhill | Arlo Underhill's powerful shot from 5.5 meters was saved, showing Ironridge Rovers' strong attacking threat early in the match despite the score remaining 0-0.
 26' [stat        ] p4 explain-llm                Line-breaking pass | Bento Calder's precise 40-meter pass at 76.6 km/h added 0.08 expected threat, helping Ironridge Rovers build momentum in a scoreless game.
 27' [chance      ] p3 explain-llm                Chance · Zeno Northam | Zeno Northam's shot from 12.8 meters went off target, missing a chance to break the deadlock as Ironridge Rovers continued pressing at 0-0.
 36' [phase       ] p5 explain-llm                Phase shift | At minute 36, Harbour City Mariners entered a siege phase with a control index of 0.695, indicating strong dominance over Ironridge Rovers (0.505), setting up sustained pressure to create scoring opportunities.
 36' [insight     ] p3 interpret-llm              Tactical read | Harbour City Mariners dominate control index at 0.695 in this siege phase, creating pressure with more shots and slightly higher xG despite lower expected threat than Ironridge Rovers.
 35' [chance      ] p4 explain-llm                Chance · Hugo Northam | At minute 35, Hugo Northam of Harbour City Mariners took a 13.6m shot at 88.9 km/h during a siege phase, but it went off target, missing a chance to break the 0-0 deadlock.
 37' [goal        ] p5 explain-llm                GOAL · HCM 0-1 IRR | Yuri Greywick scored for Ironridge Rovers at minute 37, converting a high-quality chance (xG 0.898) during a chaotic phase, giving IRR a 1-0 lead despite Harbour City Mariners' higher shot count and xG.
 37' [stat        ] p3 explain-llm                Line-breaking pass | Bento Calder delivered a fast 11.2m pass at 72.5 km/h, adding 0.06 expected threat to Ironridge Rovers' attack during a chaotic phase, helping maintain their 1-0 lead at minute 37.
 42' [stat        ] p4 explain-llm                Line-breaking pass | At minute 42, Cyro Juniper of Ironridge Rovers made a fast 16.1m pass adding 0.08 expected threat, helping maintain their 1-0 lead in a chaotic phase.
 43' [stat        ] p4 explain-llm                Line-breaking pass | At minute 43, Joss Calder of Harbour City Mariners completed a short 3.9m pass adding 0.06 expected threat, attempting to respond while trailing 0-1 in chaos.
 48' [period      ] p5 explain-llm                HCM 0-1 IRR | At the end of the 48th minute, Ironridge Rovers lead 1-0 against Harbour City Mariners, reflecting their higher expected goals (1.47 vs 0.56) and better pass completion (84% vs 81%), indicating effective control and offensive efficiency.
 48' [phase       ] p4 explain-llm                Phase shift | At minute 48, the game shifted from chaos to control with Ironridge Rovers gaining higher control index (0.64) than Harbour City Mariners (0.545), showing Ironridge's dominance in ball control after a turbulent phase.
 47' [stat        ] p3 explain-llm                Line-breaking pass | In the 47th minute, Zeno Northam of Ironridge Rovers made a fast 10.1m pass at 44.8 km/h, adding 0.07 expected threat, contributing to his team's control phase and offensive momentum while leading 1-0.
 51' [insight     ] p3 interpret-llm              Tactical read | At minute 51, despite chaos phase, Harbour City Mariners lead in control index (0.642) and Kian Juniper tops expected threat (0.235), indicating their tactical edge.
 48' [card        ] p3 explain-llm                Yellow card | At minute 48, Zeno Northam of Ironridge Rovers received a yellow card during a chaotic phase, potentially impacting team discipline while they lead 1-0 against HCM early in the second half.
 62' [stat        ] p4 explain-llm                Line-breaking pass | At minute 62, Fenn Thornby of Ironridge Rovers made a quick 9.3m pass at 55.2 km/h during a chaotic phase, adding 0.07 expected threat and maintaining their 1-0 lead, crucial for sustaining offensive momentum.
 65' [stat        ] p3 explain-llm                Line-breaking pass | At minute 65, Arlo Underhill delivered a fast 14.4m pass at 68.2 km/h for Ironridge Rovers, increasing expected threat by 0.07 while the team led 1-0, highlighting his key role in advancing attacking opportunities.
 61' [stat        ] p3 explain-llm                Line-breaking pass | At minute 61, Gus Birchall's 17m pass at 56.1 km/h during chaos added 0.06 expected threat for Ironridge Rovers, helping preserve their 1-0 advantage by progressing the ball effectively under pressure.
 68' [stat        ] p4 explain-llm                Line-breaking pass | At minute 68, Ilan Elmsworth of Ironridge Rovers completed a 34.2m pass at 75.7 km/h, adding 0.11 expected threat and helping maintain their 1-0 lead, crucial for sustaining offensive momentum.
 71' [stat        ] p5 explain-llm                Line-breaking pass | At minute 71, Gael Greywick of Harbour City Mariners made a 23.7m pass at 72.3 km/h, contributing 0.09 expected threat as they try to overcome a 0-1 deficit.
 71' [phase       ] p4 explain-llm                Phase shift | At minute 71, Ironridge Rovers regained control from chaos with a control index of 0.594 versus Harbour City Mariners' 0.572, stabilizing their play to protect their 1-0 lead.
 74' [stat        ] p4 explain-llm                Line-breaking pass | At minute 74, Harbour City Mariners' Gael Greywick completed a quick 6.3m pass at 56.7 km/h, adding 0.06 expected threat during a siege phase, aiming to break the 0-1 deficit against Ironridge Rovers.
 72' [card        ] p3 explain-llm                Yellow card | At minute 72, Ironridge Rovers' Hale Ingleby received a yellow card during a siege phase, potentially impacting team discipline while leading 1-0 over Harbour City Mariners.
 77' [stat        ] p5 explain-llm                Line-breaking pass | At minute 77, Gael Greywick of Harbour City Mariners made a fast 9.1m pass adding 0.07 expected threat, crucial as Mariners trail 0-1 in a chaotic phase, boosting their chance to equalize.
 81' [phase       ] p4 explain-llm                Phase shift | At minute 81, the game shifted from siege to chaos with Harbour City Mariners gaining higher control (0.683) than Ironridge Rovers (0.496), indicating Mariners' increased influence in this critical phase.
 81' [insight     ] p3 interpret-llm              Tactical read | At minute 81, the match remains in chaos with Harbour City Mariners leading in control index (0.618) and top xt player Kian Juniper driving their threat despite trailing 0-1.
 85' [stat        ] p5 explain-llm                Line-breaking pass | Joss Calder made a high-speed 24.6m pass adding 0.07 expected threat, crucial for Harbour City Mariners to create scoring chances late while trailing 0-1 in a chaotic phase.
 84' [chance      ] p4 explain-llm                Chance · Nilo Thornby | Nilo Thornby took a long-range shot at 33.5m with low xG of 0.005, but it was blocked, showing an attempt to break the deadlock for Harbour City Mariners despite low scoring probability.
 85' [chance      ] p4 explain-llm                Chance · Kian Juniper | Kian Juniper's fast 34.8m shot off target had minimal xG, reflecting Harbour City Mariners' urgency to score in the 85th minute while losing 0-1 in a chaotic phase.
 91' [phase       ] p4 explain-llm                Phase shift | At minute 91, Ironridge Rovers shifted from chaos to control with a control index of 0.626, surpassing Harbour City Mariners' 0.587, indicating stronger game management in a critical late phase.
 91' [chance      ] p3 explain-llm                Chance · Zeno Northam | In minute 91, Zeno Northam of Ironridge Rovers took a 14.4m shot at 94.4 km/h during control phase, but it was saved, maintaining their 1-0 lead and preserving the team's advantage.
 89' [chance      ] p4 explain-llm                Chance · Oren Birchall | At minute 89, Oren Birchall of Harbour City Mariners attempted a long-range shot at 26.7m and 105.9 km/h during control phase, but it was blocked, missing a low-probability chance to equalize.
 93' [substitution] p4 explain-llm                Substitution | At minute 93, Harbour City Mariners substituted Dario Vance for Quin Elmsworth during a chaotic phase while trailing 0-1 to IRR, aiming to inject fresh energy and possibly change the game's outcome in the final moments.
 95' [period      ] p5 explain-llm                HCM 0-1 IRR | Ironridge Rovers secured a 1-0 victory despite fewer shots, capitalizing on a higher expected goals (1.52) compared to Harbour City Mariners' 0.62, highlighting their clinical finishing in a chaotic final phase.
```

## Run 3: fan · Spanish · Harbour fan · speed 20 · semantic check + hysteresis (2026-10-19 ~23:00 CEST)
```
ticks 1980 batches 21
{
 "input_tokens": 19215,
 "output_tokens": 3431,
 "calls": 42,
 "usd": 0.01318,
 "by_agent": {
  "interpret": {
   "calls": 6,
   "input": 6365,
   "output": 484,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 8
  },
  "explain": {
   "calls": 16,
   "input": 4989,
   "output": 1395,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 0
  },
  "personalise": {
   "calls": 20,
   "input": 7861,
   "output": 1552,
   "skipped_budget": 0,
   "errors": 0,
   "tool_calls": 0
  }
 }
}
fact-check rejections 0 llm states {'azure': 39}
{'ingest': (0, 1), 'salience': (0, 0), 'interpret': (718, 2988), 'explain': (1234, 3412), 'render': (0, 0), 'personalise': (3065, 9948)}
anomalies 0 dups 0
  6' [phase       ] p4 explain-llm+personalised   Cambio de fase | ¡Ironridge Rovers dominan desde el inicio, el partido se ha vuelto un caos total!
  6' [insight     ] p3 interpret-llm+personalised Análisis táctico | Ironridge Rovers controla y pasa bien, pero el alto nivel de caos mantiene el juego abierto.
  5' [chance      ] p3 explain-llm+personalised   Oportunidad · Cyro Juniper | Cyro Juniper intentó un disparo a los 5 minutos, pero falló la oportunidad de abrir el marcador.
  6' [chance      ] p4 explain-llm+personalised   Oportunidad · Kian Juniper | ¡Kian Juniper lanzó un disparo potente pero se fue fuera, Harbour City Mariners buscando romper el empate!
 11' [chance      ] p5 explain-llm+personalised   Oportunidad · Hugo Northam | ¡Hugo Northam casi marca para Harbour City Mariners con un disparo cercano que fue salvado!
 11' [stat        ] p4 explain-llm+personalised   Pase que añade peligro | Kian Juniper lanzó un pase largo que impulsó el ataque de Harbour City Mariners en una fase caótica.
 23' [chance      ] p3 explain-llm+personalised   Oportunidad · Hugo Northam | ¡Hugo Northam de Harbour City Mariners disparó con ganas pero el portero estuvo atento!
 22' [chance      ] p2 explain-llm+personalised   Oportunidad · Cyro Juniper | Cyro Juniper de Ironridge Rovers intentó un disparo que fue salvado, manteniendo el empate.
 25' [chance      ] p2 explain-llm+personalised   Oportunidad · Bento Calder | Bento Calder de Ironridge Rovers tuvo un disparo bloqueado, sin cambiar el marcador.
 26' [chance      ] p5 explain-llm+personalised   Oportunidad · Arlo Underhill | ¡Arlo Underhill casi marca para Ironridge Rovers, pero el portero lo evitó con una gran parada!
 27' [chance      ] p3 explain-llm+personalised   Oportunidad · Zeno Northam | Zeno Northam disparó fuera y perdió una gran oportunidad para Ironridge Rovers, siguen presionando sin suerte.
 36' [insight     ] p3 interpret-llm+personalised Lectura táctica | ¡Vamos Mariners! Dominan con fuerza y ponen a Ironridge Rovers contra las cuerdas.
 35' [chance      ] p4 explain-llm+personalised   Oportunidad · Hugo Northam | Hugo Northam casi rompe el empate con un disparo rápido, ¡pero se fue desviado!
 37' [goal        ] p5 explain-llm+personalised   GOAL · HCM 0-1 IRR | ¡No puede ser! Yuri Greywick marca para Ironridge Rovers y nos ponen por detrás en el marcador.
 48' [period      ] p5 explain-llm+personalised   HCM 0-1 IRR | ¡Vamos Mariners! Dominan y merecen el empate, pero Ironridge Rovers aprovechan sus oportunidades.
 51' [insight     ] p3 interpret-llm+personalised Tactical read | ¡Kian Juniper está llevando la delantera para Harbour City Mariners en un partido muy loco!
 48' [card        ] p3 explain-llm+personalised   Yellow card | Zeno Northam de Ironridge Rovers vio amarilla y el partido sigue 1-0 para ellos contra HCM.
 66' [insight     ] p3 interpret-llm+personalised Lectura táctica | Ironridge Rovers dominan el control y las ocasiones, pero Kian Juniper destaca creando peligro para Harbour City Mariners.
 68' [stat        ] p4 explain-llm+personalised   Pase que añade peligro | ¡Ilan Elmsworth está poniendo a Ironridge Rovers a un paso de mantener el 1-0 contra Harbour City Mariners!
 72' [card        ] p3 explain-llm+personalised   Tarjeta amarilla | ¡Hale Ingleby de Ironridge Rovers se arriesga con esa amarilla en el 1-0, ojo a lo que puede pasar al final!
 81' [insight     ] p3 interpret-llm+personalised Lectura táctica | ¡Kian Juniper lo está dando todo, pero Harbour City Mariners van perdiendo 0-1 contra Ironridge Rovers!
 84' [chance      ] p4 explain-llm+personalised   Chance · Nilo Thornby | ¡Nilo Thornby lo intentó con un disparo lejano, pero Ironridge Rovers sigue ganando 1-0!
 85' [chance      ] p4 explain-llm+personalised   Chance · Kian Juniper | Kian Juniper no acertó el disparo y Harbour City Mariners siguen perdiendo 0-1 en un momento tenso.
 83' [substitution] p4 explain-llm+personalised   Substitution | Harbour City Mariners cambian a Gael Greywick por Nilo Thornby para intentar remontar el 0-1.
 91' [chance      ] p3 explain-llm+personalised   Oportunidad · Zeno Northam | ¡Zeno Northam disparó fuerte y el portero salvó el 1-0 para Ironridge Rovers en el 91!
 89' [chance      ] p4 explain-llm+personalised   Oportunidad · Oren Birchall | Oren Birchall intentó desde lejos pero el disparo fue bloqueado, Harbour City Mariners siguen sin empatar.
 86' [chance      ] p3 explain-llm+personalised   Oportunidad · Ilan Elmsworth | Ilan Elmsworth cabeceó fuera y Ironridge Rovers mantienen su ventaja mínima.
 93' [substitution] p4 explain-llm+personalised   Sustitución | ¡Vamos Harbour City Mariners! Dario Vance sale y entra Quin Elmsworth para darle la vuelta al partido.
 95' [period      ] p5 explain-llm+personalised   HCM 0-1 IRR | ¡Maldita sea, Harbour City Mariners merecían al menos un gol con tantas oportunidades claras!
REJECT 21 interpret "rejected ['leader:control: text credits Ironridge Rovers, state says Harbour City Mariners']"
```
