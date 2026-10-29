import { useState } from 'react';
import { BookOpen, Cloud, LifeBuoy } from 'lucide-react';
import { Dialog } from './ui';

const TITLES = {
  about: 'Sobre NAP',
  guide: 'Guía de uso',
  questions: 'Preguntas frecuentes',
  contact: 'Contacto y soporte',
  care: 'Uso responsable',
  accessibility: 'Accesibilidad',
};

function HelpContent({ topic, userRole }) {
  switch (topic) {
    case 'about':
      return <>
        <p className="footer-help__lead">Un espacio para acompañar la enseñanza y el aprendizaje.</p>
        <p>NAP significa <strong>Nube Académica Personal</strong>. Permite a las cátedras solicitar recursos digitales, seguir sus pedidos y acceder a sus servicios desde un mismo lugar.</p>
        <div className="footer-help__highlights">
          <section><h3>Pedí lo que necesitás</h3><p>Explorá las opciones disponibles para las actividades de tu cátedra.</p></section>
          <section><h3>Seguí cada paso</h3><p>Consultá el estado de tus solicitudes y las observaciones de administración.</p></section>
          <section><h3>Encontrá tus servicios</h3><p>Revisá cómo acceder, hasta cuándo están disponibles y cuándo renovarlos.</p></section>
        </div>
        <p>Una iniciativa de la Universidad Tecnológica Nacional, Facultad Regional Tucumán, desarrollada por Armas Mauro Nahuel, Ochoa Alejandro Iván y Medina Antonio Fabrizio para acercar herramientas digitales a la comunidad académica.</p>
      </>;
    case 'guide':
      return <>
        {!userRole && <p>Tu institución te brinda una cuenta para ingresar. Si todavía no tenés una, consultá al administrador del portal.</p>}
        <ol className="footer-help__steps">
          <li>
            <h3>Elegí un servicio</h3>
            <p>En Catálogo podés consultar las opciones disponibles (aplicaciones interactivas e infraestructura virtual). Si necesitás otra plataforma o aplicación que no esté en la lista, elegí «Otro» al crear tu pedido y describí los requerimientos pedagógicos para evaluar su incorporación.</p>
          </li>
          <li>
            <h3>Enviá tu pedido</h3>
            <p>Indicá la cátedra solicitante, el nombre de la actividad, la justificación académica y el período durante el cual se utilizará el servicio.</p>
          </li>
          <li>
            <h3>Seguí el despliegue en tiempo real</h3>
            <p>En la sección Pedidos podés monitorear el avance a través de las 4 etapas del aprovisionamiento (pedido recibido, preparación de recursos, inicio del servicio y disponibilidad). Si administración requiere más detalles, seleccioná «Responder aclaración» dentro de la solicitud.</p>
          </li>
          <li>
            <h3>Accedé y gestioná la vigencia</h3>
            <p>Una vez que el servicio esté listo, ingresá a Servicios y hacé clic en «Ver acceso» para obtener el enlace directo o las instrucciones de conexión. Si necesitás extender el uso para el siguiente ciclo académico, podés solicitar una renovación.</p>
          </li>
        </ol>
        {userRole === 'admin' && (
          <div className="footer-help__note">
            <h3>Administración del entorno</h3>
            <p>Gestioná el catálogo y biblioteca de aplicaciones en «Definiciones» y «Templates», evaluá solicitudes en «Pedidos», supervisá el hipervisor en «Consola de Operación» y controlá la capacidad en «Métricas».</p>
          </div>
        )}
      </>;
    case 'questions':
      return <div className="footer-help__questions">
        <details open><summary>¿Quién puede solicitar un servicio?</summary><p>Docentes y responsables de cátedra con cuenta activa en NAP. Si gestionás más de una cátedra, podés elegir para cuál realizar cada pedido.</p></details>
        <details><summary>¿Los estudiantes necesitan una cuenta en NAP?</summary><p>No. Los estudiantes acceden directamente al servicio o aplicación que el docente les comparta (mediante el enlace de acceso provisto), sin necesidad de registrarse en este portal.</p></details>
        <details><summary>¿Cómo accedo al servicio una vez que está listo?</summary><p>En la sección «Servicios», seleccioná el servicio y hacé clic en «Ver acceso». Se abrirá un panel con la dirección web de la aplicación o las credenciales e instrucciones de conexión correspondientes.</p></details>
        <details><summary>¿Por qué un pedido aprobado todavía no está listo?</summary><p>Un pedido aprobado entra en preparación y despliegue según su fecha programada de inicio. Podés seguir el progreso detallado de aprovisionamiento en la sección «Pedidos».</p></details>
        <details><summary>¿Qué hago si la aplicación que necesito no está en el catálogo?</summary><p>Podés crear un pedido seleccionando la opción «Otro». Describí el propósito y la herramienta buscada; el equipo de administración evaluará su compatibilidad e incorporación a la biblioteca.</p></details>
        <details><summary>¿Qué hago si necesito un servicio por más tiempo?</summary><p>Consultá la vigencia en «Servicios» y solicitá una renovación antes de la fecha límite indicando el período académico adicional.</p></details>
        <details><summary>¿Qué son los tamaños Small y Medium?</summary><p>Son perfiles estándar de recursos (1 vCPU / 512 MB RAM para Small; 2 vCPU / 1024 MB RAM para Medium) diseñados para balancear rendimiento y uso equitativo de los servidores universitarios.</p></details>
        <details><summary>¿Es obligatorio activar el segundo factor (2FA)?</summary><p>Es opcional pero recomendado. Si lo activás, se te solicitará un código temporal al ingresar. Asegurate de guardar tus códigos de recuperación en un lugar seguro.</p></details>
      </div>;
    case 'contact':
      return <>
        <p className="footer-help__lead">Estamos para orientarte.</p>
        <p>Para consultas sobre tu cuenta institucional, dudas sobre pedidos, sugerencias o soporte técnico del portal, podés comunicarte con el área responsable:</p>
        <p><strong>Correo electrónico de contacto:</strong>{' '}
          <a href="mailto:transformaciondigital@frt.utn.edu.ar" className="footer-help__email">
            transformaciondigital@frt.utn.edu.ar
          </a>
        </p>
        <p>Área de Transformación Digital — UTN Facultad Regional Tucumán.</p>
        <p>Para ayudarte más rápido, te sugerimos incluir:</p>
        <ul className="footer-help__list">
          <li>Cátedra y carrera correspondiente.</li>
          <li>Número o nombre de pedido o servicio (si corresponde).</li>
          <li>Qué intentabas hacer y captura o texto del mensaje de error, si lo hubiera.</li>
        </ul>
        <div className="footer-help__note">
          <strong>Cuidá tus datos</strong>
          <p>No envíes contraseñas ni códigos de verificación o recuperación en tus mensajes de consulta.</p>
        </div>
      </>;
    case 'care':
      return <>
        <p className="footer-help__lead">Un espacio compartido que cuidamos entre todos.</p>
        <ul className="footer-help__list">
          <li>Usá los servicios exclusivamente para las actividades académicas y de enseñanza de tu cátedra.</li>
          <li>Mantené tus contraseñas y códigos en privado. Cada persona debe utilizar su propia cuenta.</li>
          <li>Compartí el acceso a los servicios únicamente con estudiantes y miembros autorizados.</li>
          <li>Revisá los avisos y las fechas de disponibilidad para planificar tus actividades.</li>
          <li>Da de baja o no renueves aquellos servicios que hayan concluido su uso para liberar recursos en favor de otras cátedras.</li>
          <li>Si detectás un acceso inesperado o tenés dudas de seguridad, comunicate con el equipo de soporte.</li>
        </ul>
      </>;
    case 'accessibility':
      return <>
        <p className="footer-help__lead">Elegí la forma de navegar que te resulte más cómoda.</p>
        <ul className="footer-help__list">
          <li>Usá <kbd>Tab</kbd> y <kbd>Shift + Tab</kbd> para recorrer los controles y <kbd>Enter</kbd> para activarlos.</li>
          <li>En las ventanas de diálogo, la tecla <kbd>Escape</kbd> permite cerrar cuando no hay una operación en curso.</li>
          <li>Podés ampliar el texto desde las opciones de zoom de tu navegador sin perder adaptabilidad.</li>
          <li>El menú superior y la pantalla de acceso permiten alternar entre modo claro y modo oscuro.</li>
        </ul>
        <p>Si encontrás alguna dificultad o barrera de accesibilidad, podés reportarla a{' '}
          <a href="mailto:transformaciondigital@frt.utn.edu.ar" className="footer-help__email">
            transformaciondigital@frt.utn.edu.ar
          </a>.
        </p>
      </>;
    default:
      return null;
  }
}

export default function Footer({ userRole }) {
  const [topic, setTopic] = useState(null);
  const openButton = (key) => <button type="button" className="site-footer__link" aria-haspopup="dialog" onClick={() => setTopic(key)}>{TITLES[key]}</button>;
  return <>
    <footer className="site-footer">
      <div className="site-footer__inner">
        <div className="site-footer__grid">
          <div className="site-footer__brand">
            <div className="site-footer__wordmark"><Cloud aria-hidden="true" size={27} strokeWidth={1.5} /><span>NAP</span></div>
            <p>Nube Académica Personal</p>
            <p className="site-footer__tagline">Recursos para aprender.<br />Un lugar para encontrarlos.</p>
          </div>
          <nav aria-label="Conocé NAP"><h2>Conocé NAP</h2>{openButton('about')}{openButton('care')}</nav>
          <nav aria-label="Guías de NAP"><h2><BookOpen size={16} aria-hidden="true" />Guías</h2>{openButton('guide')}{openButton('questions')}</nav>
          <nav aria-label="Ayuda de NAP"><h2><LifeBuoy size={16} aria-hidden="true" />Ayuda</h2>{openButton('contact')}{openButton('accessibility')}</nav>
        </div>
        <div className="site-footer__bottom">
          <div className="site-footer__meta">
            <span>UTN · Facultad Regional Tucumán</span>
            <span className="site-footer__authors">
              Desarrollado por Armas Mauro Nahuel · Ochoa Alejandro Iván · Medina Antonio Fabrizio
            </span>
          </div>
          <span>Al servicio de la comunidad académica · {new Date().getFullYear()}</span>
        </div>
      </div>
    </footer>
    {topic && <Dialog title={TITLES[topic]} wide onClose={() => setTopic(null)} actions={<button type="button" className="btn btn-secondary" onClick={() => setTopic(null)}>Entendido</button>}>
      <div className="footer-help"><HelpContent topic={topic} userRole={userRole} /></div>
    </Dialog>}
  </>;
}
