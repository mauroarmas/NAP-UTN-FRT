import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import Footer from '../src/components/Footer.jsx';

describe('Footer y Centro de Ayuda', () => {
  it('muestra discretamente los datos del equipo de desarrollo en el pie de página', () => {
    render(<Footer userRole="catedra" />);

    expect(screen.getByText(/Armas Mauro Nahuel/i)).toBeInTheDocument();
    expect(screen.getByText(/Ochoa Alejandro Iván/i)).toBeInTheDocument();
    expect(screen.getByText(/Medina Antonio Fabrizio/i)).toBeInTheDocument();
  });

  it('abre la sección de Contacto y soporte con el correo institucional de soporte', async () => {
    const user = userEvent.setup();
    render(<Footer userRole="catedra" />);

    const contactButton = screen.getByRole('button', { name: /Contacto y soporte/i });
    await user.click(contactButton);

    expect(await screen.findByRole('heading', { name: /Contacto y soporte/i })).toBeVisible();

    const mailLink = screen.getByRole('link', { name: 'transformaciondigital@frt.utn.edu.ar' });
    expect(mailLink).toBeVisible();
    expect(mailLink).toHaveAttribute('href', 'mailto:transformaciondigital@frt.utn.edu.ar');
  });

  it('abre la guía de uso con los pasos completos del servicio y notas de rol', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Footer userRole="catedra" />);

    await user.click(screen.getByRole('button', { name: /Guía de uso/i }));
    expect(await screen.findByRole('heading', { name: /Guía de uso/i })).toBeVisible();
    expect(screen.getByText(/Elegí un servicio/i)).toBeInTheDocument();
    expect(screen.getByText(/Seguí el despliegue en tiempo real/i)).toBeInTheDocument();

    // Cátedra no ve la nota técnica de administración
    expect(screen.queryByText(/Administración del entorno/i)).not.toBeInTheDocument();

    // Cerrar diálogo
    await user.click(screen.getByRole('button', { name: /Entendido/i }));
    expect(screen.queryByRole('heading', { name: /Guía de uso/i })).not.toBeInTheDocument();

    // Rerender con rol admin muestra notas de administración
    rerender(<Footer userRole="admin" />);
    await user.click(screen.getByRole('button', { name: /Guía de uso/i }));
    expect(await screen.findByText(/Administración del entorno/i)).toBeVisible();
  });

  it('muestra las preguntas frecuentes ampliadas con respuestas útiles', async () => {
    const user = userEvent.setup();
    render(<Footer userRole="catedra" />);

    await user.click(screen.getByRole('button', { name: /Preguntas frecuentes/i }));
    expect(await screen.findByRole('heading', { name: /Preguntas frecuentes/i })).toBeVisible();
    expect(screen.getByText(/¿Quién puede solicitar un servicio\?/i)).toBeInTheDocument();
    expect(screen.getByText(/¿Cómo accedo al servicio una vez que está listo\?/i)).toBeInTheDocument();
    expect(screen.getByText(/¿Qué son los tamaños Small y Medium\?/i)).toBeInTheDocument();
  });
});
