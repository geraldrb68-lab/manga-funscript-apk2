"""Vocabulario del español para el verificador de coherencia del OCR (ocr_verify.py).

No es un diccionario completo: es el vocabulario que aparece en diálogos de manga/cómic (palabras de uso diario, familia, cuerpo,
escuela, sentimientos, acción, humor, jerga) más un generador de formas verbales y de género/número. Sirve para tres cosas:
  1. saber si una palabra leída por el OCR «existe» (si no, y el OCR dudó, se corrige o se descarta);
  2. proponer la corrección más cercana cuando el OCR confundió letras (l/I/1, rn/m, o/0, acentos perdidos…);
  3. comprobar que una frase tiene palabras reales en la proporción esperada.
Las palabras que falten no rompen nada: un nombre propio o una palabra rara con buena confianza del OCR se conserva igual.
"""
from __future__ import annotations

import unicodedata

# ----------------------------------------------------------------------------------------------- palabras funcionales y fijas
FUNC = """
a ante bajo cabe con contra de desde durante en entre hacia hasta mediante para por según sin so sobre tras versus vía
el la los las un una unos unas lo al del este esta esto estos estas ese esa eso esos esas aquel aquella aquello aquellos aquellas
mi mis tu tus su sus nuestro nuestra nuestros nuestras vuestro vuestra vuestros vuestras
yo tú vos él ella ello usted nosotros nosotras vosotros vosotras ellos ellas ustedes me te se nos os le les
mí ti sí conmigo contigo consigo
y e o u ni pero sino mas aunque porque pues que si como cuando donde cual cuyo cuya cuyos cuyas mientras
qué quién quiénes cuál cuáles cómo cuándo dónde cuánto cuánta cuántos cuántas adónde
quien quienes cuanto cuanta cuantos cuantas
no sí tal vez quizá quizás acaso nunca jamás siempre ya aún todavía ahora antes después luego entonces enseguida pronto tarde temprano
hoy ayer mañana anoche anteayer
aquí allí allá acá ahí cerca lejos arriba abajo adelante atrás dentro fuera encima debajo alrededor delante detrás junto
muy mucho mucha muchos muchas poco poca pocos pocas bastante demasiado demasiada demasiados tanto tanta tantos tantas tan más menos casi apenas solo sola solos solas
todo toda todos todas nada nadie algo alguien alguno alguna algunos algunas ninguno ninguna ningún ningunos otro otra otros otras
mismo misma mismos mismas cada varios varias ambos ambas cualquier cualquiera demás ciertos ciertas cierto cierta
uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince veinte treinta cuarenta cincuenta sesenta setenta
ochenta noventa cien ciento mil millón millones primero primera primeros primeras segundo segunda tercero tercera tercer último última
sí claro vale bueno bien mal mejor peor así tampoco también incluso además aparte sólo solamente exactamente realmente
ah oh eh ay uf uy ey hey oye oiga mira mire vaya bah puf hmm mm eh ja jaja jeje jiji uh ugh aj ajá aha ups huy
hola adiós chao chau gracias perdón perdona perdone disculpa disculpe lo siento por favor de nada bienvenido bienvenida
señor señora señorita don doña sensei senpai kouhai kun chan san sama oni onii nii nee onee neesan niisan onichan oneechan
sí no tal cual donde adonde como cuando mientras ojalá hasta incluso salvo excepto menos según durante mediante
""".split()

# ----------------------------------------------------------------------------------------------- verbos
AR = """
hablar amar andar ayudar bailar buscar caminar cantar cenar cerrar cocinar comprar contestar cuidar dejar desayunar descansar
desear dibujar dudar echar empezar encantar entrar esperar estudiar explicar faltar firmar gastar gritar gustar lavar levantar
limpiar callar llamar llegar llevar llorar mandar mirar molestar nadar necesitar olvidar pagar parar pasar pelear pensar perdonar practicar
preguntar preparar prestar probar quedar quitar rezar robar saludar sacar sentar sonar soñar tirar tocar tomar trabajar tratar
usar viajar visitar volar votar ganar matar odiar arreglar atacar avisar besar cambiar cargar celebrar cobrar colgar cortar cruzar
cuestionar curar dar disfrutar doblar durar enamorar encontrar enfadar enseñar entregar enviar escapar escuchar evitar fallar
fingir forzar funcionar gozar guardar herir imaginar importar indicar informar inventar invitar jugar lanzar lograr luchar marchar
meter mostrar notar observar ocupar odiar opinar orar organizar parecer peinar pintar planear pisar pegar apretar abrazar acabar
aceptar acompañar acordar acostar acusar admitir agarrar agradecer ahorrar alegrar alejar alimentar almorzar amenazar anunciar
aparecer apostar apoyar aprobar aprovechar armar arrastrar arrepentir asustar atar atender aterrar aumentar ayudar bajar bañar
barrer borrar botar brillar burlar calentar calmar cansar cargar casar castigar cazar chocar cocer colocar comentar compartir
comprobar concentrar confesar confiar confirmar conquistar consultar contar controlar convencer convertir copiar cumplir
decidir declarar defender demostrar depender derrotar desaparecer descubrir desmayar despertar destruir detener dirigir
disculpar disparar distraer divertir doler dormir duchar elegir emocionar empujar encender encerrar enfermar engañar entender
enterar entrenar equivocar escoger esconder escribir esforzar espantar estirar excitar existir extrañar fastidiar felicitar
fijar formar frotar fumar gemir girar golpear gustar heredar hundir ignorar impedir imponer incluir insistir intentar interesar
interrumpir ir juntar jurar lamentar lamer lastimar leer lucir manejar mantener marcar mejorar mentir merecer mojar montar
morder morir mover mudar nacer negar nevar obedecer obligar ocurrir ofrecer oír oler pedir permitir perseguir pertenecer
pesar picar pertenecer pisar poseer preocupar presentar presumir prometer proteger provocar publicar recibir reconocer
recordar recuperar reír rendir repetir resistir resolver respirar responder retirar reunir revisar rodear rogar romper saltar
salvar secar seguir sentir separar servir significar sobrevivir sonreír soportar sorprender sostener subir sudar sufrir
sugerir suponer temblar temer terminar tener tragar traer traducir transformar tropezar unir vencer vender vestir vigilar
vivir volver
""".split()

# verbos con cambio de raíz: e->ie, o->ue, e->i, u->ue
E_IE = set("""cerrar empezar pensar comenzar despertar sentar encender entender perder querer recomendar negar nevar apretar
calentar confesar sentir mentir preferir sugerir divertir herir convertir hervir temblar tropezar atender defender
encerrar""".split())
O_UE = set("""contar encontrar recordar mostrar probar volar volver poder dormir morir mover doler sonar soñar costar
demostrar almorzar colgar rogar apostar aprobar acostar mover morder oler resolver soler torcer volcar forzar
llover cocer""".split())
E_I = set("""pedir seguir servir repetir elegir vestir medir reír sonreír competir impedir perseguir corregir rendir
despedir concebir""".split())
U_UE = {"jugar"}
IR_VERBS = set("""vivir escribir recibir abrir subir salir sentir dormir morir pedir seguir servir repetir elegir vestir medir
decidir partir sufrir cumplir permitir existir insistir interrumpir imponer incluir unir descubrir admitir reír sonreír
convertir mentir preferir sugerir divertir herir competir impedir perseguir corregir rendir despedir construir destruir
huir oír asistir añadir cubrir discutir dividir emitir escribir exigir prohibir pulir resistir reunir sobrevivir
atender""".split())
ER_VERBS = set("""comer beber correr aprender vender temer deber romper meter ver leer creer poder querer saber tener hacer poner
volver mover perder entender defender ofrecer conocer parecer nacer crecer merecer obedecer agradecer aparecer
desaparecer pertenecer reconocer ofrecer vencer convencer proteger coger escoger esconder resolver responder
suceder tejer toser caer traer valer oler doler envolver devolver mantener sostener detener contener obtener
componer proponer suponer imponer disponer""".split())

# formas irregulares completas (las más usadas); lo regular lo genera el programa
IRREG = """
ser soy eres es somos sois son era eras éramos erais eran fui fuiste fue fuimos fuisteis fueron seré serás será seremos seréis serán
sería serías seríamos seríais serían sea seas seamos seáis sean fuera fueras fuéramos fuerais fueran sé sed siendo sido
estar estoy estás está estamos estáis están estaba estabas estábamos estabais estaban estuve estuviste estuvo estuvimos estuvisteis
estuvieron estaré estarás estará estaremos estaréis estarán estaría estarías estaríamos estaríais estarían esté estés estemos
estéis estén estuviera estuvieras estuviéramos estuvierais estuvieran estando estado
ir voy vas va vamos vais van iba ibas íbamos ibais iban iré irás irá iremos iréis irán iría irías iríamos iríais irían vaya vayas
vayamos vayáis vayan yendo ido ve id
haber he has ha hemos habéis han había habías habíamos habíais habían hube hubiste hubo hubimos hubieron habré habrás habrá
habremos habrán habría habrías habríamos habrían haya hayas hayamos hayan hubiera hubieras hubiéramos hubieran habiendo habido hay
tener tengo tienes tiene tenemos tenéis tienen tenía tenías teníamos teníais tenían tuve tuviste tuvo tuvimos tuvisteis tuvieron
tendré tendrás tendrá tendremos tendréis tendrán tendría tendrías tendríamos tendríais tendrían tenga tengas tengamos tengáis
tengan tuviera tuvieras tuvieran teniendo tenido ten tened
hacer hago haces hace hacemos hacéis hacen hacía hacías hacíamos hacían hice hiciste hizo hicimos hicisteis hicieron haré harás
hará haremos haréis harán haría harías haríamos harían haga hagas hagamos hagáis hagan hiciera hicieras hicieran haciendo hecho
hecha hechos hechas haz haced
decir digo dices dice decimos decís dicen decía decías decíamos decían dije dijiste dijo dijimos dijisteis dijeron diré dirás dirá
diremos diréis dirán diría dirías diríamos dirían diga digas digamos digan dijera dijeras dijeran diciendo dicho dicha dichos di
decid
poder puedo puedes puede podemos podéis pueden podía podías podíamos podían pude pudiste pudo pudimos pudieron podré podrás podrá
podremos podrán podría podrías podríamos podrían pueda puedas podamos puedan pudiera pudieras pudieran pudiendo podido
querer quiero quieres quiere queremos queréis quieren quería querías queríamos querían quise quisiste quiso quisimos quisieron
querré querrás querrá querremos querrán querría querrías querríamos querrían quiera quieras queramos quieran quisiera quisieras
quisieran queriendo querido quiere
saber sé sabes sabe sabemos sabéis saben sabía sabías sabíamos sabían supe supiste supo supimos supieron sabré sabrás sabrá
sabremos sabrán sabría sabrías sabríamos sabrían sepa sepas sepamos sepan supiera supieras supieran sabiendo sabido sabe
ver veo ves ve vemos veis ven veía veías veíamos veían vi viste vio vimos vieron veré verás verá veremos verán vería verías
veríamos verían vea veas veamos vean viera vieras vieran viendo visto vista vistos vistas
dar doy das da damos dais dan daba dabas dábamos daban di diste dio dimos disteis dieron daré darás dará daremos darán daría
darías daríamos darían dé des demos den diera dieras dieran dando dado da dame dime dale
venir vengo vienes viene venimos venís vienen venía venías veníamos venían vine viniste vino vinimos vinieron vendré vendrás
vendrá vendremos vendrán vendría vendrías vendríamos vendrían venga vengas vengamos vengan viniera vinieras vinieran viniendo
venido ven
poner pongo pones pone ponemos ponéis ponen ponía ponías ponían puse pusiste puso pusimos pusieron pondré pondrás pondrá pondremos
pondrán pondría pondrías pondrían ponga pongas pongamos pongan pusiera pusieras pusieran poniendo puesto puesta puestos puestas pon
salir salgo sales sale salimos salís salen salía salías salían salí saliste salió salieron saldré saldrás saldrá saldremos
saldrán saldría saldrías saldrían salga salgas salgamos salgan saliera salieras salieran saliendo salido sal
traer traigo traes trae traemos traéis traen traía traías traían traje trajiste trajo trajimos trajeron traeré traerá traería
traiga traigas traigamos traigan trajera trajeras trajeran trayendo traído trae
oír oigo oyes oye oímos oís oyen oía oías oían oí oíste oyó oyeron oiré oirás oirá oiría oiga oigas oigamos oigan oyera oyendo oído
caer caigo caes cae caemos caéis caen caía caías caían caí caíste cayó cayeron caeré caerá caería caiga caigas caigamos caigan
cayera cayendo caído
creer creo crees cree creemos creéis creen creía creías creían creí creíste creyó creyeron creeré creerá creería crea creas
creamos crean creyera creyendo creído leer leo lees lee leemos leen leía leí leyó leyeron leeré leería lea leas leamos lean
leyera leyendo leído
conocer conozco conoces conoce conocemos conocen conocía conocí conoció conocieron conoceré conocería conozca conozcas conozcamos
conozcan conociera conociendo conocido parecer parezco pareces parece parecen parecía pareció parecieron parezca parezcan
parecido ofrecer ofrezco ofreces ofrece ofrezca agradecer agradezco agradece agradezca merecer merezco mereces merece merezca
nacer nazco naces nace nacen nació nacieron nacido crecer crezco creces crece crecen creció crezca
valer valgo vales vale valemos valen valía valió valdrá valdría valga
caber quepo cabes cabe cabemos caben cabía cupo cupieron cabrá cabría quepa
soler suelo sueles suele solemos suelen solía solían
huir huyo huyes huye huimos huyen huía huí huyó huyeron huiré huiría huya huyendo huido
construir construyo construyes construye construimos construyen construí construyó construyeron construiré construiría
construya construyendo construido destruir destruyo destruyes destruye destruyen destruyó destruyeron destruya destruyendo
destruido
reír río ríes ríe reímos reís ríen reía reías reían reí reíste rió rieron reiré reirá reiría ría rías riamos rían riendo reído
sonreír sonrío sonríes sonríe sonreímos sonríen sonreía sonreí sonrió sonrieron sonreiré sonreiría sonría sonriendo sonreído
freír frío fríe frió frito
ir ve vete vámonos vamos
morir muero mueres muere morimos mueren moría morí moriste murió murieron moriré moriría muera mueran muriendo muerto muerta
muertos muertas
vuelto vuelta abierto abierta escrito escrita roto rota cubierto cubierta
dormir duermo duermes duerme dormimos dormís duermen dormía dormí dormiste durmió durmieron dormiré dormiría duerma duerman
durmiendo dormido
""".split()

# ----------------------------------------------------------------------------------------------- sustantivos
NOUNS = """
abuelo abuela abuelos madre padre padres hijo hija hijos hermano hermana hermanos hermanas tío tía primo prima familia esposo esposa
marido mujer hombre niño niña niños chico chica chicos chicas amigo amiga amigos amigas novio novia pareja vecino vecina jefe
jefa compañero compañera profesor profesora maestro maestra alumno alumna estudiante doctor doctora médico enfermera policía
ladrón ladrona rey reina príncipe princesa héroe heroína villano monstruo demonio ángel dios diosa diablo fantasma bruja mago
vampiro lobo gato gata perro perra pájaro pez caballo vaca cerdo ratón animal bestia dragón
cabeza cara ojo ojos nariz boca labio labios lengua diente dientes oreja oreja pelo cabello cuello hombro brazo mano manos dedo dedos
pecho espalda cintura cadera pierna pie pies rodilla piel corazón sangre hueso cuerpo mente alma voz lágrima lágrimas
casa hogar cuarto habitación cama baño cocina sala puerta ventana pared techo suelo piso escalera jardín calle ciudad pueblo país
mundo tierra cielo mar playa río montaña bosque isla campo escuela colegio clase aula instituto universidad trabajo oficina tienda
mercado restaurante hotel hospital iglesia templo castillo torre puente parque estación tren autobús coche carro auto moto bicicleta
avión barco
día noche mañana tarde semana mes año hora minuto segundo momento tiempo vez veces rato instante verano invierno otoño primavera
lunes martes miércoles jueves viernes sábado domingo
agua fuego aire viento luz sombra oscuridad lluvia nieve sol luna estrella estrellas nube trueno rayo tormenta fuerza poder magia
espada arma pistola escudo flecha bomba llave carta libro cuaderno lápiz papel mesa silla ropa camisa falda vestido zapato zapatos
sombrero bolsa mochila regalo dinero precio cuenta comida cena almuerzo desayuno pan arroz carne pescado fruta manzana leche café
té vino cerveza dulce pastel helado chocolate
amor odio miedo dolor felicidad tristeza alegría ira rabia vergüenza orgullo sueño sueños secreto mentira verdad vida muerte
guerra paz batalla pelea lucha victoria derrota destino futuro pasado presente historia cuento idea problema pregunta respuesta
razón motivo causa culpa error falta favor ayuda cosa cosas lugar sitio parte lado forma manera modo nombre palabra frase
número fiesta juego deporte música canción baile película foto televisión teléfono móvil ordenador computadora internet mensaje
llamada beso besos abrazo sonrisa risa grito sonido ruido silencio sexo placer deseo pasión cariño ternura
señal marca camino viaje aventura misión plan trabajo equipo grupo gente persona personas gracia cuidado suerte milagro locura
orden regla ley paz fin final principio comienzo vez cumpleaños boda examen nota tarea deberes recreo
""".split()

# ----------------------------------------------------------------------------------------------- adjetivos (forma masculina)
ADJ = """
bueno malo grande pequeño nuevo viejo joven bonito feo guapo lindo hermoso bello fuerte débil rápido lento alto bajo largo corto
gordo flaco delgado feliz triste enfadado cansado ocupado libre solo seguro cierto falso verdadero extraño raro normal especial
importante difícil fácil posible imposible necesario peligroso tranquilo caliente frío duro blando suave dulce amargo rico pobre
cercano lejano mismo propio igual distinto diferente ocupado enfermo sano muerto vivo loco tonto listo inteligente estúpido
cruel amable gentil honesto sincero valiente cobarde tímido orgulloso celoso curioso divertido aburrido interesante terrible
horrible increíble maravilloso fantástico genial perfecto excelente tremendo enorme gigante mojado húmedo seco limpio sucio
desnudo vestido cerrado abierto lleno vacío listo preparado dispuesto sorprendido asustado nervioso emocionado preocupado
avergonzado confundido perdido herido cansado embarazada casado soltero blanco negro rojo azul verde amarillo rosa morado
naranja gris marrón dorado plateado primero último único cualquier mejor peor mayor menor sagrado maldito bendito
""".split()

# ----------------------------------------------------------------------------------------------- adverbios y varios
MISC = """
realmente verdaderamente probablemente seguramente claramente obviamente evidentemente finalmente rápidamente lentamente
fácilmente tranquilamente exactamente simplemente solamente totalmente completamente absolutamente definitivamente
inmediatamente directamente actualmente normalmente generalmente especialmente principalmente personalmente
mente por qué porque porqué conque sino también tampoco además aunque mientras entonces pues bueno vale venga vamos vamonos
oye oiga mira fíjate mirad cuidado socorro auxilio ayuda alto basta espera esperen esperad corre corran rápido deprisa despacio
cállate callaos silencio tranquilo tranquila calma ánimo suerte salud felicidades enhorabuena bienvenido adelante pasa pasen
siéntate siéntese gracias muchas muchísimas perdón disculpa lo siento claro desde luego por supuesto de acuerdo está bien
no importa da igual qué tal cómo estás cómo está buenos días buenas tardes buenas noches hasta luego hasta pronto nos vemos
amigo amiga idiota imbécil tonto tonta estúpido estúpida maldito maldita maldición demonios diablos carajo mierda joder
puta puto coño polla verga culo tetas pechos
""".split()

# ----------------------------------------------------------------------------------------------- generador
_ACC = str.maketrans("áéíóúü", "aeiouu")


def strip_accents(w: str) -> str:
    """Quita acentos pero conserva la ñ."""
    out = []
    for ch in unicodedata.normalize("NFD", w):
        if unicodedata.category(ch) == "Mn" and ch != "̃":
            continue
        out.append(ch)
    s = unicodedata.normalize("NFC", "".join(out))
    return s


def _stem_change(stem: str, kind: str) -> str:
    """Cambia la última vocal de la raíz según el tipo (e→ie, o→ue, e→i, u→ue)."""
    pairs = {"ie": ("e", "ie"), "ue": ("o", "ue"), "i": ("e", "i"), "uue": ("u", "ue")}
    a, b = pairs[kind]
    i = stem.rfind(a)
    return stem[:i] + b + stem[i + 1:] if i >= 0 else stem


def conjugate(inf: str) -> set[str]:
    """Formas de un verbo regular (con cambios de raíz y de ortografía más comunes)."""
    forms = {inf}
    if inf.endswith("se"):
        inf = inf[:-2]
    end = inf[-2:] if inf.endswith(("ar", "er", "ir")) else ("ír" if inf.endswith("ír") else inf[-2:])
    if end == "ír":
        end = "ir"
        inf = inf[:-2] + "ir"
    if end not in ("ar", "er", "ir"):
        return forms
    stem = inf[:-2]
    kind = "ie" if inf in E_IE else "ue" if inf in O_UE else "i" if inf in E_I else "uue" if inf in U_UE else ""
    sc = _stem_change(stem, kind) if kind else stem                # raíz con cambio (formas fuertes)
    ir_weak = stem
    if end == "ir" and kind in ("ie", "i"):
        ir_weak = _stem_change(stem, "i")                           # sintió, pidió, sintiendo
    elif end == "ir" and kind in ("ue",):
        ir_weak = stem[:stem.rfind("o")] + "u" + stem[stem.rfind("o") + 1:]   # durmió, durmiendo
    # ortografía: -car -gar -zar (antes de e) y -ger -gir -guir -cer -cir (antes de o/a)
    pre_e = stem
    if inf.endswith("car"):
        pre_e = stem[:-1] + "qu"
    elif inf.endswith("gar"):
        pre_e = stem + "u"
    elif inf.endswith("zar"):
        pre_e = stem[:-1] + "c"
    pre_oa = stem
    if inf.endswith(("ger", "gir")):
        pre_oa = stem[:-1] + "j"
    elif inf.endswith("guir"):
        pre_oa = stem[:-1]
    elif inf.endswith(("cer", "cir")) and len(stem) > 1 and stem[-2] not in "aeiou" + "áéíóú" and False:
        pre_oa = stem[:-1] + "z"
    elif inf.endswith(("cer", "cir")) and len(stem) > 1 and stem[-2] in "aeiou":
        pre_oa = stem + "z"                                         # conocer → conozco
    elif inf.endswith(("cer", "cir")):
        pre_oa = stem[:-1] + "z"
    strong = (sc,) * 3 + (stem, stem, sc)                          # yo tú él nos vos ellos

    def strong_base(i):
        return strong[i]
    if end == "ar":
        pres = ["o", "as", "a", "amos", "áis", "an"]
        pret = ["é", "aste", "ó", "amos", "asteis", "aron"]
        imp = ["aba", "abas", "aba", "ábamos", "abais", "aban"]
        subj = ["e", "es", "e", "emos", "éis", "en"]
        isub = ["ara", "aras", "ara", "áramos", "arais", "aran"]
        ger, part = "ando", "ado"
        impv = ["a", "e", "ad", "en"]
    elif end == "er":
        pres = ["o", "es", "e", "emos", "éis", "en"]
        pret = ["í", "iste", "ió", "imos", "isteis", "ieron"]
        imp = ["ía", "ías", "ía", "íamos", "íais", "ían"]
        subj = ["a", "as", "a", "amos", "áis", "an"]
        isub = ["iera", "ieras", "iera", "iéramos", "ierais", "ieran"]
        ger, part = "iendo", "ido"
        impv = ["e", "a", "ed", "an"]
    else:
        pres = ["o", "es", "e", "imos", "ís", "en"]
        pret = ["í", "iste", "ió", "imos", "isteis", "ieron"]
        imp = ["ía", "ías", "ía", "íamos", "íais", "ían"]
        subj = ["a", "as", "a", "amos", "áis", "an"]
        isub = ["iera", "ieras", "iera", "iéramos", "ierais", "ieran"]
        ger, part = "iendo", "ido"
        impv = ["e", "a", "id", "an"]
    for i, suf in enumerate(pres):
        base = strong[i] if i in (0, 1, 2, 5) else stem
        if i == 0 and end != "ar":
            base = sc if kind in ("ie", "ue", "uue") or kind == "i" else pre_oa
            if inf.endswith(("cer", "cir", "ger", "gir", "guir")):
                base = pre_oa
        forms.add(base + suf)
        if i == 0 and inf.endswith(("cer", "cir")) and len(stem) > 1 and stem[-2] in "aeiou":
            forms.add(stem[:-1] + "zco")
            forms.add(stem + "zco")
    for i, suf in enumerate(pret):
        base = stem
        if i == 0 and end == "ar":
            base = pre_e
        if i in (2, 5) and end == "ir" and kind:
            base = ir_weak
        if i in (2, 5) and end in ("er", "ir") and stem and stem[-1] in "aeiouáéíóú":
            suf = suf.replace("ió", "yó").replace("ieron", "yeron")      # leyó, cayó, construyó
        forms.add(base + suf)
        if i in (2, 5) and end in ("er", "ir") and stem and stem[-1] in "aeiou":
            forms.add(stem + ("yó" if i == 2 else "yeron"))
    for suf in imp:
        forms.add(stem + suf)
    for suf in (("é", "ás", "á", "emos", "éis", "án")):
        forms.add(inf + suf)
    for suf in ("ía", "ías", "ía", "íamos", "íais", "ían"):
        forms.add(inf + suf)
    for i, suf in enumerate(subj):
        if end == "ar":
            base = strong[i] if i in (0, 1, 2, 5) else stem
            if inf.endswith("car") and base.endswith("c"):
                base = base[:-1] + "qu"
            elif inf.endswith("gar") and base.endswith("g"):
                base = base + "u"
            elif inf.endswith("zar") and base.endswith("z"):
                base = base[:-1] + "c"
        else:
            if i in (0, 1, 2, 5):
                base = pre_oa if inf.endswith(("ger", "gir", "guir", "cer", "cir")) else strong[i]
            else:
                base = ir_weak if end == "ir" and kind else (pre_oa if inf.endswith(("ger", "gir", "guir", "cer", "cir")) else stem)
        forms.add(base + suf)
    for suf in isub:
        base = ir_weak if (end == "ir" and kind) else stem
        forms.add(base + suf)
    gbase = ir_weak if (end == "ir" and kind) else stem
    ger_form = gbase + ger
    if stem and stem[-1] in "aeiouáéíóú" and end in ("er", "ir"):
        ger_form = stem + "yendo"
    forms.add(ger_form)
    for suf in (part, part[:-1] + "a", part + "s", part[:-1] + "as"):
        forms.add(stem + suf)
    for i, suf in enumerate(impv):
        base = sc if i in (0, 1, 3) and kind else stem
        if i == 1 and end != "ar" and inf.endswith(("ger", "gir", "cer", "cir", "guir")):
            base = pre_oa
        if i == 1 and end == "ar" and inf.endswith(("car", "gar", "zar")):
            base = pre_e
        forms.add(base + suf)
    return {f for f in forms if f}


_CLITICS = ("me", "te", "se", "lo", "la", "los", "las", "le", "les", "nos", "os")


def build() -> set[str]:
    """Todas las formas conocidas (minúsculas, con acentos)."""
    words: set[str] = set()
    words.update(FUNC)
    words.update(w.lower() for w in IRREG)
    words.update(MISC)
    for v in set(AR) | ER_VERBS | IR_VERBS:
        words.update(conjugate(v))
    for v in set(AR):
        words.update(conjugate(v))
    for n in NOUNS:
        words.add(n)
        if n.endswith(("a", "e", "o")):
            words.add(n + "s")
        elif n.endswith(("í", "ú")):
            words.update({n + "es", n + "s"})
        elif n.endswith("z"):
            words.add(n[:-1] + "ces")
        elif n.endswith("s"):
            words.add(n)
        elif n.endswith(("ción", "sión")):
            words.add(n[:-2] + "ones")
        elif n.endswith("ón"):
            words.add(n[:-2] + "ones")
        elif n.endswith(("l", "r", "n", "d", "j", "y")):
            words.add(n + "es")
        else:
            words.add(n + "s")
        if n.endswith("o"):
            words.add(n[:-1] + "a")
            words.add(n[:-1] + "as")
        if n.endswith("or"):
            words.add(n + "a")
            words.add(n + "as")
    for a in ADJ:
        words.add(a)
        if a.endswith("o"):
            words.update({a[:-1] + "a", a + "s", a[:-1] + "as"})
            words.add(a[:-1] + "amente")
            words.add(a[:-1] + "ísimo")
            words.add(a[:-1] + "ísima")
        elif a.endswith("z"):
            words.add(a[:-1] + "ces")
        elif a.endswith(("e", "a")):
            words.add(a + "s")
        elif a.endswith(("l", "r", "n", "d")):
            words.update({a + "es", a + "a", a + "as"} if a.endswith(("or", "ón", "án")) else {a + "es"})
        else:
            words.add(a + "s")
    return {w.lower() for w in words if w}


def strip_clitics(w: str, known) -> str | None:
    """«dímelo» → «di»; «hacerlo» → «hacer»; «mírame» → «mira». Devuelve la raíz conocida o None."""
    cur = w
    for _ in range(3):
        for c in sorted(_CLITICS, key=len, reverse=True):
            if cur.endswith(c) and len(cur) > len(c) + 1:
                base = cur[: -len(c)]
                for cand in (base, strip_accents(base)) + tuple(_re_accent(base)):
                    if cand in known:
                        return cand
                cur = base
                break
        else:
            return None
    return None


def _re_accent(base: str):
    """Variantes con acento en la penúltima vocal (mírame → mira, dámelo → da)."""
    out = []
    vowels = "aeiou"
    for i in range(len(base) - 1, -1, -1):
        ch = base[i]
        if ch in "áéíóú":
            out.append(base[:i] + ch.translate(_ACC) + base[i + 1:])
            break
    return out
