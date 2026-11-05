const FIELDS = [['vcpus', 'vCPU'], ['ram_mb', 'RAM (MiB)'], ['disk_gb', 'Disco (GiB)']];
const format = (value) => value == null ? '—' : new Intl.NumberFormat('es-AR').format(value);

export default function PanelCapacidad({ evaluacion }) {
  if (!evaluacion) return null;
  const cost = evaluacion.costo_incremental;
  const zero = FIELDS.every(([field]) => cost?.[field] === 0);
  const destination = evaluacion.seleccion?.destino;
  return <section aria-label="Evaluación de la asignación" className="card" style={{ padding: 16 }}>
    <p>{zero ? 'Registrar estas condiciones no reserva recursos ni enciende el contenedor.'
      : evaluacion.justificacion_requerida ? 'La asignación requiere justificar la sobreasignación lógica.'
        : 'Selección evaluada. Confirmá los recursos, destino y fechas antes de aprobar.'}</p>
    {destination && <p>Destino: {destination.nodo} / {destination.storage}</p>}
    <table><thead><tr><th>Recurso</th><th>Libre antes</th><th>Costo incremental</th><th>Libre previsto</th></tr></thead>
      <tbody>{FIELDS.map(([field, label]) => <tr key={field}><th scope="row">{label}</th>
        <td>{format(evaluacion.libre_antes?.[field])}</td><td>{format(cost?.[field])}</td><td>{format(evaluacion.libre_despues?.[field])}</td>
      </tr>)}</tbody>
    </table>
    {evaluacion.restricciones_fisicas?.length > 0 && <p role="alert">El destino tiene límites físicos que impiden aprobar: {evaluacion.restricciones_fisicas.join(', ')}.</p>}
    {evaluacion.vigencia_efectiva && <p>Vigencia efectiva: {evaluacion.vigencia_efectiva.desde || evaluacion.vigencia_efectiva.inicio_at} → {evaluacion.vigencia_efectiva.hasta || evaluacion.vigencia_efectiva.fin_exclusivo_at}.</p>}
    <p>Una evaluación vence a los 60 segundos. Editar la selección requiere evaluarla nuevamente.</p>
  </section>;
}
