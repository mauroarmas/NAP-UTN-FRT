/**
 * Los números que el administrador necesita para decidir sobre un pedido.
 *
 * Muestra, además del saldo libre, **cómo quedaría si aprueba**. Sin esa
 * proyección hay que hacer la resta de cabeza en cada decisión, que es
 * exactamente donde se cometen los errores que la reserva busca evitar.
 *
 * Los valores vienen de `GET /pedidos/{id}/evaluacion` y se recalculan en el
 * servidor cada vez: nunca se cachean.
 */

const MAGNITUDES = [
  { clave: 'vcpus', etiqueta: 'vCPUs', unidad: '' },
  { clave: 'ram_mb', etiqueta: 'RAM', unidad: ' MB' },
  { clave: 'storage_gb', etiqueta: 'Disco', unidad: ' GB' },
];

export default function PanelCapacidad({ evaluacion }) {
  if (!evaluacion) return null;

  const { capacidad, costo, libre_si_aprueba: libreDespues, excede_capacidad: excede,
          consumo_catedra: consumoCatedra, pedido } = evaluacion;

  return (
    <div className="panel-capacidad">
      <p className="capacidad-riesgo">
        Cátedra <strong>{pedido?.catedra?.nombre}</strong> — ya tiene{' '}
        {consumoCatedra.vcpus} vCPU, {consumoCatedra.ram_mb} MB de RAM y{' '}
        {consumoCatedra.storage_gb} GB de disco desplegados.
      </p>

      <div className="capacidad-grid">
        {MAGNITUDES.map(({ clave, etiqueta, unidad }) => {
          const quedaria = libreDespues[clave];
          const insuficiente = quedaria < 0;
          return (
            <div
              key={clave}
              className={`capacidad-item${insuficiente ? ' is-excedido' : ''}`}
            >
              <div className="capacidad-item__label">{etiqueta} libre</div>
              <div className="capacidad-item__valor">
                {capacidad.libre[clave]}
                {unidad}
              </div>
              <div className="capacidad-item__proyectado">
                Este pedido pide {costo[clave]}
                {unidad} → quedarían {quedaria}
                {unidad}
              </div>
            </div>
          );
        })}
      </div>

      {excede && (
        <div className="capacidad-aviso">
          <strong>Aprobar esto compromete más capacidad de la disponible.</strong>{' '}
          Podés hacerlo igual, pero tenés que dejar una justificación: queda
          registrada junto con la aprobación.
        </div>
      )}

      <p className="capacidad-riesgo">
        Del total físico ({capacidad.fisica.vcpus} vCPU,{' '}
        {capacidad.fisica.ram_mb} MB), hay {capacidad.reservado.vcpus} vCPU y{' '}
        {capacidad.reservado.ram_mb} MB <strong>reservados</strong> por pedidos ya
        aprobados que todavía no se desplegaron.
      </p>

      {capacidad.ram_en_riesgo_mb > 0 && (
        <p className="capacidad-riesgo">
          Si todos los servicios pausados se reactivaran a la vez harían falta{' '}
          {capacidad.ram_en_riesgo_mb} MB de RAM
          {capacidad.ram_en_riesgo_mb > capacidad.libre.ram_mb && (
            <strong> — más de lo que hay libre, así que algunas reactivaciones
            van a fallar</strong>
          )}
          .
        </p>
      )}
    </div>
  );
}
