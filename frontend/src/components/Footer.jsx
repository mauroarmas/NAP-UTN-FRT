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
        <p>Una iniciativa de la Universidad Tecnológica Nacional, Facultad Regional Tucumán, para acercar herramientas digitales a la comunidad académica.</p>
      </>;
    case 'guide':
      return <>
        {!userRole && <p>Tu institución te brinda una cuenta para ingresar. Si todavía no tenés una, consultá al administrador del portal.</p>}
        <ol className="footer-help__steps">
          <li><h3>Elegí un servicio</h3><p>En Catálogo, consultá las opciones disponibles. Si necesitás otra plataforma o aplicación, elegí «Otro» al crear un pedido y describí lo que buscás; administración evaluará su incorporación al catálogo.</p></li>
          <li><h3>Enviá tu pedido</h3><p>Indicá la cátedra, el nombre de la solicitud, la justificación pedagógica y el período durante el que lo vas a utilizar.</p></li>
          <li><h3>Consultá su estado</h3><p>En Pedidos podés seguir el avance y leer las observaciones. Si te piden una aclaración, abrí el detalle, elegí «Responder aclaración» y reenviá la información para su revisión.</p></li>
          <li><h3>Accedé y revisá la vigencia</h3><p>Cuando el servicio esté listo, consultá su acceso en Servicios. Si necesitás más tiempo, solicitá una renovación.</p></li>
        </ol>
        {userRole === 'admin' && <div className="footer-help__note"><h3>Si administrás NAP</h3><p>Revisá las solicitudes, comunicá los ajustes necesarios y confirmá que cada servicio esté listo antes de entregarlo a la cátedra.</p></div>}
      </>;
    case 'questions':
      return <div className="footer-help__questions">
        <details open><summary>¿Quién puede solicitar un servicio?</summary><p>El responsable de una cátedra con cuenta en NAP. Si tenés varias cátedras asignadas, podés elegir para cuál hacer el pedido.</p></details>
        <details><summary>¿Los estudiantes necesitan una cuenta en NAP?</summary><p>No. El docente comparte las instrucciones para utilizar el servicio de la cátedra. Algunas aplicaciones pueden requerir su propia cuenta de acceso.</p></details>
        <details><summary>¿Por qué un pedido aprobado todavía no está listo?</summary><p>Puede estar esperando la fecha de inicio o su preparación. Revisá el estado del pedido y del servicio; una aprobación por sí sola no significa que ya puedas utilizarlo.</p></details>
        <details><summary>¿Qué hago si necesito un servicio por más tiempo?</summary><p>Revisá su vigencia en Servicios y solicitá una renovación. Si hay un intervalo entre períodos, el servicio puede permanecer pausado durante ese tiempo.</p></details>
        <details><summary>¿Es obligatorio activar el segundo factor?</summary><p>Es opcional. Si lo activás, se te pedirá al ingresar. Guardá los códigos de recuperación en un lugar privado para usarlos si perdés el acceso a tu aplicación autenticadora.</p></details>
      </div>;
    case 'contact':
      return <>
        <p className="footer-help__lead">Estamos para orientarte.</p>
        <p>Para consultas sobre tu cuenta, pedidos o servicios, contactá al <strong>administrador del portal de tu institución</strong>.</p>
        <p><strong>Contacto de soporte:</strong> por definir.</p>
        <p>Para ayudarte más rápido, incluí:</p>
        <ul className="footer-help__list"><li>La cátedra a la que pertenece la consulta.</li><li>El número de pedido o servicio, si corresponde.</li><li>Qué intentabas hacer y el mensaje que apareció.</li></ul>
        <div className="footer-help__note"><strong>Cuidá tus datos</strong><p>No envíes contraseñas ni códigos de verificación o recuperación.</p></div>
      </>;
    case 'care':
      return <>
        <p className="footer-help__lead">Un espacio compartido que cuidamos entre todos.</p>
        <ul className="footer-help__list"><li>Usá los servicios para las actividades académicas de tu cátedra.</li><li>Mantené tus contraseñas y códigos en privado. Cada persona debe utilizar su propia cuenta.</li><li>Compartí el acceso a los contenidos sólo con las personas que correspondan.</li><li>Revisá los avisos y las fechas de disponibilidad para planificar tus actividades.</li><li>Si detectás un acceso inesperado o tenés dudas, comunicate con el administrador.</li></ul>
      </>;
    case 'accessibility':
      return <>
        <p className="footer-help__lead">Elegí la forma de navegar que te resulte más cómoda.</p>
        <ul className="footer-help__list"><li>Usá Tab y Shift + Tab para recorrer los controles y Enter para activarlos.</li><li>En los diálogos, Escape permite cerrar cuando no hay un paso obligatorio o un envío en curso.</li><li>Podés ampliar el texto desde las opciones de zoom de tu navegador.</li><li>El menú de tu cuenta permite elegir modo claro u oscuro.</li></ul>
        <p>Si encontrás una barrera para usar el portal, contale al administrador en qué pantalla ocurre y qué necesitabas hacer.</p>
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
          <span>UTN · Facultad Regional Tucumán</span>
          <span>Al servicio de la comunidad académica · {new Date().getFullYear()}</span>
        </div>
      </div>
    </footer>
    {topic && <Dialog title={TITLES[topic]} wide onClose={() => setTopic(null)} actions={<button type="button" className="btn btn-secondary" onClick={() => setTopic(null)}>Entendido</button>}>
      <div className="footer-help"><HelpContent topic={topic} userRole={userRole} /></div>
    </Dialog>}
  </>;
}
