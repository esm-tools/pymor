# EMD: Gitter für die zonalen Schnitte von AWI-ESM3-4-2-veg-HR

Stand 2026-08-17. Vier Dateien unserer CMIP7-Ausgabe haben kein flächiges Gitter, sondern
eine Breitenachse und eine Beckenachse. Für die gibt es im Register keinen passenden
`horizontal_grid_cell`. Das ist eine Stage-1-Registrierung, wie bei g235, g236 und g238.

## Zuerst: bei uns ist etwas uneinheitlich

Das würde ich vor dem Einreichen geradeziehen, sonst zementiert der Eintrag den Fehler.
Gemessen an cli114:

| Datei | Punkte | Bereich | Schritt | Konvention |
|---|---|---|---|---|
| `msftm_tavg-ol-hyb-sea` | 181 | −90.0 bis 90.0 | 1° | Werte auf **ganzen** Grad |
| `msftm_tavg-rho-hyb-sea` | 180 | −89.5 bis 89.5 | 1° | Werte auf **halben** Grad |
| `hfbasin` | 166 | −77.5 bis 87.5 | 1° | halbe Grad, beschnitten |
| `sltbasin` | 166 | −77.5 bis 87.5 | 1° | halbe Grad, beschnitten |

Die unteren drei sind dieselbe Konvention, einmal global und zweimal auf den Ozeanbereich
gekürzt. Die oberste ist eine andere: 181 Punkte auf ganzen Grad von Pol zu Pol sind
Zellkanten, keine Zellmitten. Dieselbe Variable `msftm`, einmal auf Tiefe und einmal auf
Dichte gerechnet, landet also auf zwei unvereinbaren Achsen. Ursache ist vermutlich, dass
die beiden Rechenwege verschieden binnen.

**Vorschlag:** alles auf 180 Zellen mit Mitten auf halben Grad, −89.5 bis 89.5. Das ist
die Konvention, die drei der vier schon benutzen, es sind saubere 1°-Zellen mit Kanten auf
ganzen Grad, und die Pole liegen auf Zellkanten statt auf Zellmitten. Wo eine Variable
physikalisch nur einen Teilbereich abdeckt, wird auf diesem Gitter maskiert statt die
Achse zu kürzen. Dann beschreibt **ein** Eintrag alle vier Dateien.

## Was zu registrieren wäre

Ein `horizontal_grid_cell` für ein zonales Mittelungsgitter:

| Feld | Wert | Anmerkung |
|---|---|---|
| `grid_type` | `regular-latitude-longitude` | es gibt keinen eigenen Typ für zonale Achsen |
| `n_cells` | 180 | eine Zelle je Breitenband |
| `x_resolution` | 360 | jedes Band umspannt alle Längen |
| `y_resolution` | 1 | 1° in der Breite |
| `units` | `degree` | |
| `southernmost_latitude` | −90 | südliche Kante der ersten Zelle |
| `westernmost_longitude` | 0 | |
| `region` | `global` | |
| `temporal_refinement` | `static` | |
| `description` | Zonal mean grid: 180 latitude bands of 1 degree, each spanning all longitudes. Used for basin-integrated and zonally averaged ocean transports. | |

Die Beckenachse (`basin`, drei Werte: Atlantik/Arktis, Indopazifik, global) ist **keine**
Gitterdimension, sondern eine Zeichenkoordinate aus dem CMIP7-CV. Die gehört nicht in die
Registrierung.

## Zur Einordnung, falls die Frage kommt

Warum ein eigener Eintrag und nicht das native Gitter: die Daten liegen nicht mehr auf dem
FESOM-Mesh. Sie sind über Längengrade und über Becken integriert, das Ergebnis hat mit den
3146761 Knoten nichts mehr zu tun. Aktuell tragen die vier Dateien `g130` und behaupten
damit ein Gitter, auf dem sie nicht liegen. Genau dieselbe Sorte Fehler wie die 142
Dateien mit `g113` in cli109.

Nicht Teil dieses Antrags, aber verwandt und noch offen: 30 weitere Dateien sind globale
Mittel und haben überhaupt keine horizontale Achse. Dafür ist laut DKRZ der Bereich der
ersten 100 Label reserviert, die Entscheidung steht noch aus. `g190` im Register
("A single grid cell for the entire globe", `n_cells: 1`) sieht passend aus, ist aber
nicht unserer, wird von niemandem referenziert, und beschreibt eine echte Zellgeometrie mit
Ursprung und Ausdehnung, die unsere Dateien gar nicht mitliefern. Deshalb bewusst nicht
benutzt.

## Danach in pycmor

`grid_label` für die vier Regeln in
`awi-esm3-veg-hr-variables/lrcs_ocean/cmip7_awiesm3-veg-hr_lrcs_ocean.yaml` auf das neue
Label setzen. Sie erben es aktuell aus dem `inherit`-Block des Tiers, deshalb steht dort
`g130`.
