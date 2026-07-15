Sí, primero que nada como para terminar más planes del trabajo, este, ¿cómo será el tema de un poco más definido los roles que tenemos porque hemos armado más o menos lo
yo lo que quiero es que tener, a ver, ustedes distribúyanse como quieran
dentro de lo que es la estructura del funcionamiento, lo que vamos a armar, va a haber gente que tiene, le digamos así, se persona uno que tiene eh un rol más relacionado con el tema de la infraestructura.
Sí, perdón. Este, ya nos repartimos más o menos los temas. Yo yo el encargado de hacer el software, el del almacenamiento y poder la infraestructura, ¿no?
Eh, sí. Sí. O sea, hemos dividido uno del software y los dos la parte de todo el armado del físico, digamos,
infraestructura.
Sí,
dentro de lo que es infraestructura es configuración de dispositivos de networking. En este caso el booter Microtic,
¿sí?
Y el switch Microtic. Y la instalación de los nodos de Proc M.
Bien. El almacenamiento era C o
el almacenamiento va a ser Trunas.
Trunas.
Trunas.
Sí. O sea, que es el otro rol y después del tema del software, ¿qué es lo que tiene que estar por encima de eso?
Eh, más o menos, profe, ¿cómo serían las credenciales? O sea, entiendo que una cátedra sería, tendría como un usuario, un usuario por cátedra más o menos.
Mir lo que hacemos en la cátedra y cada uno de ustedes entra con su usuario y administra entender un único espacio. En el caso de las cátedras, cada cátedra tendría su espacio.
O sea, no hay algún administrador rol, o sea, perdón, una persona administrador general. Hay un administrador general. Pero ese es el que va a armar todo el
ese les daría los usuarios, digamos,
es el que administra el acceso a la plataforma y todo eso.
O sea, sería este un username, password y este el 2FA, digamos.
Exacto.
Por cátedra. Okay.
Claro. O sea, vos en vez de entrar a lo que sería el espacio de virtualización, en este caso,
en vez de virtualización tendría los nombres de las cátedras que tendrían cada uno su espacio para administrar.
Bien, profe.
Eso en el caso de lo que sería la infraestructura como servicio.
Sí.
En el caso de la paz implicaría que vos tendrías que armar todo un, suponete, una especie de servicio, conjunto de servicios como supase, no sé si lo conocen.
Bueno, en realidad el objetivo ellos van a desarrollar el sistema.
Sí, también.
Entonces, lo que va a hacer son los requerimientos del del pedido de recurso para la carta.
Está bien. Sí, para yo quiero terminar más, manejarlo internamente. Vamos por parte después si estaban hablando Sí, eso va a ser más o menos ya cuando empecemos a trabajar. Exactamente el primer punto que tenemos que desar el
requerimiento.
Y después el tema de eh el manejo de suponerte cuando vos tenés una si yo tengo la posibilidad de instalar suponerte una serie de servicios con un solo comando, un solo esquema de instalación, ver qué vamos a usar, si vamos a si vamos a usar directamente la API del el mismo Prox para interactuar con el software y vos desde el software administrar esos servicios, ¿entendés? O sea, no no que que sea un acceso directo a Promo,
sino que el software sea
está como intermediario,
portal el portal de gestión.
Exact. Exactamente. Yo estuve averiguando, lo voy a hacer en Python, es decir, porque Python tiene una biblioteca que se llama Proxmoxer, que ya te da todas las appis ya como ya construida, digamos. O sea, vos tendrías que definir clase,
pero son todos los lenguajes tienen, ¿no? O sea, No me interesa el tipo de lenguaje, me interesa que sea lo que buscamos. Sí. O sea, el ejemplo de administración de de servicio lo tienen que tomar de cualquier interfaz de administración de nube dividiendo los diferentes tipos de servicios. Esa es más o menos la idea.
Perfecto, profe. Este, otra consulta, este digamos nosotros en Proxm, en la materia, tenemos los contenedores, digamos, del 100 al este,
sí,
del 100 al, no sé, 200 y tanto. Eso sería de la misma forma, por ejemplo, un, por ejemplo, que la cátedra, no sé, de análisis matemático tenga contenedores de 1000 al tanto. No, no,
no, no, no interesa. No, ¿por qué? A ver, ese número lo mejor que podemos hacer es evitar y administrar ese número.
Sí,
lo mejor. ¿Por qué? Porque no me interesa. Es un número de ID interno,
¿entendés? No, no sirve nada más que para que se reconozca internamente el el servicio y ese servicio corre dentro del otro. Nosotros leemos No vamos a modificar la plataforma de virtualización, lo que buscamos es monitorear los recursos y administrar.
Monitorear,
bien, sobre todo los recursos. Bien,
no se olviden, el portal también tiene que contemplar la administración de los Microtic, por ejemplo.
Ajá.
También hay librería de acceso, todo eso, pero
perfecto.
Todo eso se puede armar.
Eh,
¿tendría algún dominio particular, digamos, o sería como NAP? También sería
Napfrt, ese que tengo ahora nada más que va a ir al portal.
Perfecto.
Va a ir al portal y de ahí lo vamos a encaminar hacia otro lado.
Sí. Este, bueno, habíamos dicho también que el software estaría viido en un este en un nodo aparte, digamos. Puede ser.
Sí, sí. Más o menos. ¿Cuánto de recurso tendría? ¿Sabes decirme? ¿O eso lo estamos viendo? No, para ese software,
sí, para el software exclusivamente, sí, como para yo ir,
no sé, lo mínimo posible. No sé cuánto necesita. Hagamos, o sea, Claro. Claro. Por a ver, pensemos cómo hacer el crecimiento de acuerdo a lo que vos elijas como stack tecnológico. Pongamos
eso, másí. Perfecto.
No, no quiero. A ver, como regla de laburo, no damos disco genérico más grande que de 8 GB.
Listo.
O sea, si podemos menos, mejor.
Bueno, voy a intentar ponerle cuatro, máximo ocho. Ya de eso no me paso. Máximo ocho. No, no creo que en base ocho. No, no chance. Eso, pero a ver si ya No ve estado hoy en la clase a la tarde.
No, no puedo estar no puedo venir. Había un su compañero que le quedaba chico los ocho gig porque no le entraban todas las librerías.
No, pero
bueno, lo planteó todo por eso, o sea,
pero bueno, pero todos los gustos, o sea, como digo, hay chicos que están muy avanzados
y otros que no. Entonces, la idea es que esto le dé por lo menos una experiencia antes que se vaya de la facultad problema de estas características, si no
pero bueno, hubo un plateo de eso. Hoy también estuvo Iñaki, no sé si lo ubican bueno presentando el
Sí, la extensión sí la pasó antes y la estamos usando muy reído, por Dios. Pero bueno,
maravilloso, ¿no? Pero me parece excepcional. Ya he dicho que lo divulguen todo,
por Dios, en vez de lo que tenemos.
Eh, profe,
se puede, se puede entre paréntesis se pueden inscribir hacer todas las gestiones del software sin problemas. Sí,
sí. Ustedes a finales, a todo, lo han hecho con eso.
Sí, anda. O sea, te cambia el tan solo el front la vista,
pero el resto tiene funcionaría completa.
Creo sigue siendo la misma llamada de fondo, solamente cambia lo que se ve.
Sí.
Este
hace se meses están tratando de cambiar el por divertido. Hoy le mandó un mes
hace mes llevó casi un año.
Por Dios, hay una solución, hermano. No, no, ya le pasé todo, me burlé toda la tarde. Buenas,
buenas, buenas,
don,
profe, ¿no? Entonces, digamos, eh, una cátedra, una misma cátedra, digamos, una misma persona se daría de alta su propio usuario o alguien le daría su usuario.
No, no, el software tiene que crear, el software tiene que gestionar todo. Olvidémonos de Progm. Prmx va a ser nuestro back.
Sí.
Sí. Entonces, el software tiene que leer, los usuarios tiene que tener la posibilidad de asignar roles.
Ajá.
Que ya están todos predefinidos.
Sí. Eh, sí,
pero no me queda claro de O sea, alguien de, no sé, análisis matemático,
¿no? Alguien de análisis matemático va a pedir.
Va a pedir. Ajá. Lo pediría acá.
Pedir. Claro. Y va a haber un va a pedir por el sistema.
El sistema va a notificar que hay un pedido. Se le va a responder.
Ahora sí me quedo claro.
No hay personas en el medio. Olvidém, ¿no?
Ajá.
Se cuál es la idea hacemos el software y el día de mañana una gente lo va a administrarlo. O sea, no no quiero
pensemos pensemos en
para adelante, por Dios.
Eliminemos
un poco superior
eliminemos el factor de rol que normalmente tiene dos partes y se siente.
Bien. Y digamos daría de alta un contenedor para su base de datos según su requerimiento.
Según su requerimiento. Ped un servicio. Él puede pedir un servidor o un contenedor. o puede pedir que le instalemos determinado software o eso que sirve o nosotros ofrecerle, o sea, eso es abierto,
pero el software tiene que hacer el seguimiento del pedido hasta el impactado del mismo.
Muy bien. Como si fuera un software, un software de gestión de pedidos. No sé si han hecho, han usado AWS cuando crean una BPS o alguna máquina, te da el diagrama de trans, o sea, te va pasando por el diagrama de transición de estado que lo conocemos nosotros, te va mostrando los estados por los que pasa hasta que está Entonces, cuando está cuando cuando hasta aquí impacta y se arma la BPS y responde, entonces podemos ir viendo en qué estado está
la persona puede ir viendo en qué estado está
y la palabra final para aprobar eso lo daría
es cuando ya esté efectivizado adestramos.
Perfecto. O sea, que el software también tendría que tener un un panel de administrador.
Claro, de administrador de todos los recursos disponibles para no entrar al prome. Bien,
la idea es coincitir con el software y que ese sea nuestro elemento de comunicación.
La idea es lo menos posible interactuar con próximos,
¿no? No, el usuario con progno lo menos posible.
Listo. Porque nadie sabe, o sea, porque en definitiva, si nosotros le mandamos una cátedra de análisis, un acceso progno
es lo mismo que
Sí, no tiene idea.
Claro, no tiene idea. Sí, sí. En todo caso te voy a pedir que me dé un BPS y que pongan tal software nosotros vamos contenedores,
o sea, el propósito de ustedes automatizar todo que que venga. O sea, la idea es pensar en un middleware, o sea, en un software intermediando todos los recursos con que vamos a contar.
Joya, bien,
buenísimo.
Lo que sí vamos a tener que definir son los límites. Hasta cuánto le puedes dar una cátedra y qué le puedes dar.
Ah, eso está bueno.
Eso sí se tiene que definir.
Hay modelos template definido, por ejemplo. con tamaños de servidores,
mm
de contenedores que tienen por defecto 256 g, tienen tal cosa, tal otra template.
Tenés modelos que funcionan
en las nubes reales que claramente nosotros no vamos a poder usar porque acá si usamos más de 8 GB utilizamos todo un nodo, pero hacer nuestros propios templates siguiendo el estándar, o sea, estándar entendés que te permite armar eso.
Claro. Sí, sí,
sí. Por ejemplo, la virtual CPO, la idea sería que se apague, digamos, y que la CPU atienda a otros que se está usando los cuatro contor contenedores como lo tenemos. Ahora tenemos, tengo en este momento hay 49, casi 100 contenedores para todos ustedes. O sea, en el aula, en el grupo de virtualización tengo 100 contenedores andando con las soluciones
joya
en producción con menos de 8 GB.
Joya,
o sea, que haciendo más o menos una analogía, estaríamos más o menos con un caso de lo que sería un nodo.
Mhm. ¿Entendés? Vamos a tener cinco. Entonces tenemos para hacer cosas que sean no grandes
prestaciones en cuanto a recursos. No podemos montar nuestra propia ID, pero podemos hacer un prototipo para mostrar cómo la podríamos consumir o con una gente gestionándola por detrás,
diferentes roles, hacer algo divertido.
Pero eso después vamos ahora primero con
lo más elemental, administrar recursos.
Bien.
Bien.
Cuando ustedes esto lo van a tener para cuándo
eso también queremos hablar digamos digamos, o sea, ¿cuándo podríamos arrancar? Porque tenemos que
creo que lo primero que tienen que presentar el nombre del de lo que quieren hacer y el plan de trabajo.
Sí, nosotros queramos ya para inscribir una práctica supervisada, digamos.
Bueno, inscríbanse y yo lo que diría es que me dejen libre esta semana.
La semana que viene yo ya empiezo a tomar los trabajos de
de liberdas.
Tratemos de mantener una configuración elemental, una configuración base ya con todo armado en el prototipo antes de irnos a las vacaciones para que puedan laborar.
Bien,
este,
claro, o sea, armo el plan de trabajo, lo presento y la idea
como si estuvieran trabajando ya.
Sí, como si yo estuvieran trabajando. Trabaj aula magna y el aula magna está funcionando porque no es zoom uno le Sí. Yo, bueno, por ejemplo, tengo ventaja, si estoy en el software puedo estar, o sea, programándolo, no no hace falta que venga tando tan seguido, tal vez como los chicos, digamos. Correcto. No, no hace falta que vengan. O sea, si lo armamos, ya pasó la configuración, hay queaburar, empezar a distribuir los recursos. ¿Qué vamos a distribuir de lo del storage? ¿Cómo vamos a hacer? Si los contenedores vamos a tener procesamiento en los nodos, nada más y el storage va a servir de almacenamiento de todos los discos que armemos. O sea, es un tema de diseño ya, pero después de hacer la base.
Perfecto, perfecto.
Perfecto, perfecto.
¿Cómo lo vemos? Lo veo bien, lo veo. Claro.
Bueno,
sí. Este,
pero si les queda algo pendiente, lo pueden ir pidiendo que te pidan por WhatsApp o por
Sí, probablemente escribamos algo para presentar en el CONA.
Ajá. Buenísimo. Perfecto.
Así que vayan pensando. Bueno, terminemos formalizar esto. Lo otro es un
profe por ahí. Este, bueno, no sé si estoy j**\*\*\*** mucho, digamos, pero no sé si sería posible que tal vez hagamos un grupo de WhatsApp, digamos, mejor de lo menos posible, pero Antes hago un grupo,
sí, por favor, porque por ahí seguramente durante caminos surjan dudas y bueno,
sí, WhatsApp no me gusta, pero soy de poca bola, la verdad, el tema WhatsApp no puedo hacer la lailación de los temas.
Sí, que tengamos un medio, digamos, porque por ahí una pregunta que puede hacer él me puede servir a mí también.
Un grupo de práctica supervisada y los meto ahí adentro.
Buenísimo, por favor. Así,
le pongo un canal nap y ahí quiera.
Buenísima. Buenísima, profe. Listo.
Y vamos para adelante.
Y vamos a armar y segur papeles. Este ahí lo de la cruz.
Hay que firmar a veces ya todo a veces y este nos dijo que bañar y pasado podir al final este justamente Madrid puede quedar porque tiene que ir saludar. Ustedes tenemos que
usted tendría que ser
