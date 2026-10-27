const { useEffect, useMemo, useState } = React;

const API = {
  login: "/api/usuarios/login",
  register: "/api/usuarios/registro/paciente",
  registerProfessional: "/api/usuarios/registro/profesional",
  profile: "/api/usuarios/yo",
  professionals: "/api/catalogo-medicos/profesionales",
  services: (specialtyId) => `/api/catalogo-medicos/especialidades/${specialtyId}/servicios`,
  // El paciente solo ve los horarios libres (ADR 003); 503 si reservas no responde.
  freeAvailability: (email, desde, hasta) => `/api/catalogo-medicos/profesionales/${encodeURIComponent(email)}/disponibilidades?desde=${desde}&hasta=${hasta}&solo_libres=true`,
  ownAvailability: (desde, hasta) => `/api/catalogo-medicos/mis-disponibilidades?desde=${desde}&hasta=${hasta}`,
  createAvailability: "/api/catalogo-medicos/disponibilidades",
  deleteAvailability: (id) => `/api/catalogo-medicos/disponibilidades/${id}`,
  reservations: "/api/reservas/mis-turnos",
  agenda: (desde, hasta) => `/api/reservas/agenda?desde=${desde}&hasta=${hasta}`,
  reserve: "/api/reservas/turnos",
  cancel: (id) => `/api/reservas/turnos/${id}/cancelar`,
};

const SPECIALTIES = [
  { id: 1, name: "Clínica médica" },
  { id: 2, name: "Pediatría" },
  { id: 3, name: "Cardiología" },
  { id: 4, name: "Dermatología" },
];

function Icon({ name, size = 20 }) {
  const paths = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9" /><path d="M9 20v-6h6v6" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    calendar: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3M21 19V5a2 2 0 0 0-2-2h-5" /></>,
    edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z" /></>,
    trash: <><path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function initials(user) { return `${user?.nombre?.[0] || ""}${user?.apellido?.[0] || ""}`.toUpperCase(); }
// Fecha local (AAAA-MM-DD). toISOString usa UTC: después de las 21 h en Montevideo daría mañana.
function isoDate(date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
function todayPlus(days) { const date = new Date(); date.setDate(date.getDate() + days); return date; }
function displayDate(value, options = { weekday: "short", day: "numeric", month: "short" }) { return new Intl.DateTimeFormat("es-UY", options).format(new Date(`${value}T12:00:00`)); }

async function request(url, options = {}) {
  const token = localStorage.getItem("turnos_token");
  const response = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(typeof body.detail === "string" ? body.detail : "No se pudo completar la solicitud.");
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function Login({ onLogin }) {
  const [role, setRole] = useState("PACIENTE");
  const [registering, setRegistering] = useState(false);
  const [form, setForm] = useState({ email: "", contrasena: "", nombre: "", apellido: "", documento: "", telefono: "", matricula: "", id_especialidad: "1" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  async function submit(event) {
    event.preventDefault(); setError(""); setLoading(true);
    try {
      if (registering) {
        const endpoint = role === "PROFESIONAL" ? API.registerProfessional : API.register;
        const data = role === "PROFESIONAL"
          ? { email: form.email, contrasena: form.contrasena, nombre: form.nombre, apellido: form.apellido, matricula: form.matricula, id_especialidad: Number(form.id_especialidad) }
          : form;
        await request(endpoint, { method: "POST", body: JSON.stringify(data) });
      }
      const token = await request(API.login, { method: "POST", body: JSON.stringify({ email: form.email, contrasena: form.contrasena }) });
      localStorage.setItem("turnos_token", token.access_token); onLogin();
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }
  function changeRole(nextRole) { setRole(nextRole); setRegistering(false); setError(""); }
  return <main className={`login-screen ${role === "PROFESIONAL" ? "professional-theme" : ""}`}><form className={`login-card ${registering ? "register-card" : ""}`} onSubmit={submit}>
    <div className="brand"><div className="brand-mark"><Icon name="calendar" size={19} /></div><strong>Turnos médicos</strong></div>
    <div className="role-switcher"><button type="button" className={role === "PACIENTE" ? "selected" : ""} onClick={() => changeRole("PACIENTE")}>Paciente</button><button type="button" className={role === "PROFESIONAL" ? "selected" : ""} onClick={() => changeRole("PROFESIONAL")}>Profesional</button></div>
    <h1>{registering ? "Creá tu cuenta" : role === "PROFESIONAL" ? "Acceso profesional" : "Bienvenido"}</h1>
    <p className="muted">{registering ? role === "PROFESIONAL" ? "Registrate para comenzar a gestionar tu agenda." : "Registrate como paciente para comenzar a reservar turnos." : role === "PROFESIONAL" ? "Gestioná tu agenda y consultá tus próximos turnos." : "Ingresá para gestionar tus turnos."}</p>
    {registering && <div className="form-grid"><Field label="Nombre" value={form.nombre} onChange={update("nombre")} required /><Field label="Apellido" value={form.apellido} onChange={update("apellido")} required /></div>}
    <Field label="Email" type="email" value={form.email} onChange={update("email")} required />
    <Field label="Contraseña" type="password" minLength="8" value={form.contrasena} onChange={update("contrasena")} required />
    {registering && role === "PACIENTE" && <div className="form-grid"><Field label="Documento" value={form.documento} onChange={update("documento")} required /><Field label="Teléfono (opcional)" value={form.telefono} onChange={update("telefono")} /></div>}
    {registering && role === "PROFESIONAL" && <div className="form-grid"><Field label="Matrícula" value={form.matricula} onChange={update("matricula")} required /><div className="form-field"><label>Especialidad</label><select value={form.id_especialidad} onChange={update("id_especialidad")} required>{SPECIALTIES.map((specialty) => <option key={specialty.id} value={specialty.id}>{specialty.name}</option>)}</select></div></div>}
    {error && <div className="form-error">{error}</div>}
    <button className="primary-button full-width" disabled={loading}>{loading ? "Ingresando..." : registering ? "Crear cuenta" : "Ingresar"}</button>
    <p className="auth-switch">{registering ? "¿Ya tenés una cuenta?" : role === "PROFESIONAL" ? "¿Todavía no te registraste como profesional?" : "¿Todavía no tenés una cuenta?"} <button type="button" className="link-button" onClick={() => { setRegistering(!registering); setError(""); }}>{registering ? "Ingresar" : role === "PROFESIONAL" ? "Registrate acá" : "Registrate"}</button></p>
  </form></main>;
}

function Field({ label, type = "text", value, onChange, required = false, minLength, min }) {
  return <div className="form-field"><label>{label}</label><input type={type} value={value} onChange={onChange} required={required} minLength={minLength} min={min} /></div>;
}

function Topbar({ user, page, setPage, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return <header className="topbar"><div className="top-actions"><div className="profile-wrapper"><button className="avatar-button" onClick={() => setMenuOpen(!menuOpen)}>{initials(user)}</button>{menuOpen && <div className="profile-menu"><p><strong>{user.nombre} {user.apellido}</strong><br /><span className="muted">{user.email}</span></p><button onClick={() => { setMenuOpen(false); setPage("profile"); }}>Ver perfil</button><button onClick={onLogout}><Icon name="logout" size={15} /> Cerrar sesión</button></div>}</div><div className="icon-pill"><button className={`icon-button ${page === "home" ? "active" : ""}`} onClick={() => setPage("home")}><Icon name="home" /></button><button className={`icon-button ${page === "notifications" ? "active" : ""}`} onClick={() => setPage("notifications")}><Icon name="bell" /></button></div></div></header>;
}

function Sidebar({ page, setPage, professional }) {
  const items = professional ? [["home", "Inicio", "home"], ["schedule", "Horarios", "calendar"], ["notifications", "Notificaciones", "bell"], ["profile", "Mi perfil", "user"]] : [["home", "Inicio", "home"], ["professionals", "Profesionales", "users"], ["notifications", "Notificaciones", "bell"], ["profile", "Mi perfil", "user"]];
  return <aside className="sidebar"><div className="brand"><div className="brand-mark"><Icon name="calendar" size={19} /></div><strong>Turnos</strong></div><nav className="nav-list">{items.map(([id, label, icon]) => <button key={id} className={`nav-button ${page === id ? "active" : ""}`} onClick={() => setPage(id)}><Icon name={icon} /><span>{label}</span></button>)}</nav></aside>;
}

function PatientHome({ user, reservations, details, setPage, onCancel }) {
  return <><Hero user={user} professional={false} setPage={setPage} /><section><div className="section-heading"><div><h2>Mis reservas</h2><p>Revisá tus próximos turnos.</p></div><button className="link-button" onClick={() => setPage("professionals")}>Nueva reserva →</button></div>{reservations.length ? <div className="reservation-grid">{reservations.map((item) => <ReservationCard key={item.id_turno} reservation={item} details={details[item.id_turno]} onCancel={onCancel} />)}</div> : <Empty text="Aún no tenés reservas." action="Buscar un profesional" onAction={() => setPage("professionals")} />}</section></>;
}

function Hero({ user, professional, setPage }) {
  return <section className="hero"><div className="hero-copy"><span className="page-kicker">{professional ? "Panel profesional" : "Portal del paciente"}</span><h1>Hola, {user.nombre}!</h1><p>{professional ? "Organizá tu agenda y revisá las próximas consultas de tus pacientes." : "Encontrá el profesional que necesitás y reservá tu próximo turno de forma rápida y sencilla."}</p><button className="primary-button" onClick={() => setPage(professional ? "schedule" : "professionals")}>{professional ? "Administrar horarios" : "Agendar nuevo turno"} <span aria-hidden="true">→</span></button></div><div className="hero-card"><Icon name="calendar" size={28} /><strong>{professional ? "Tu agenda, bajo control" : "Tu salud merece tiempo"}</strong><small>{professional ? "Mantené actualizada tu disponibilidad para recibir nuevas consultas." : "Consultá profesionales y elegí el horario que mejor te quede."}</small></div></section>;
}

function ReservationCard({ reservation, details, onCancel, professional = false }) {
  const cancelled = reservation.estado !== "RESERVADO";
  // Sin nombre (usuarios no respondió, ADR 009): se muestra el email del paciente.
  const patientName = [reservation.nombre_paciente, reservation.apellido_paciente].filter(Boolean).join(" ") || reservation.email_paciente || "Paciente";
  const title = professional ? patientName : details?.serviceName || details?.specialty || "Turno médico";
  const subtitle = professional ? `${reservation.horario_inicio.slice(0, 5)} - ${reservation.horario_fin.slice(0, 5)}` : `${details?.serviceName && details?.specialty ? `${details.specialty} · ` : ""}${reservation.horario_inicio.slice(0, 5)} - ${reservation.horario_fin.slice(0, 5)}`;
  return <article className={`card reservation-card ${cancelled ? "reservation-cancelled" : ""}`}><div className="reservation-top"><div><h3>{title}</h3><p className="muted">{subtitle}</p></div><div className="date-badge">{displayDate(reservation.fecha)}</div></div><div className="reservation-top"><span className={`status ${cancelled ? "cancelled" : ""}`}>{cancelled ? "CANCELADO" : "CONFIRMADO"}</span>{!cancelled && onCancel && <button className="link-button" onClick={() => onCancel(reservation.id_turno)}>Cancelar</button>}</div></article>;
}

function PatientProfessionals({ professionals, reservations, onReserve }) {
  const [query, setQuery] = useState(""); const [openEmail, setOpenEmail] = useState(null);
  const filtered = professionals.filter((item) => `${item.nombre} ${item.apellido} ${item.especialidad}`.toLowerCase().includes(query.toLowerCase()));
  return <><PageHeader kicker="Encontrá atención" title="Profesionales" text="Elegí un profesional y encontrá el horario ideal para tu consulta." /><div className="toolbar"><input className="search-input" placeholder="Buscar por nombre o especialidad" value={query} onChange={(e) => setQuery(e.target.value)} /></div><section className="professional-list">{filtered.map((professional) => <ProfessionalCard key={professional.email} professional={professional} reservations={reservations} isOpen={openEmail === professional.email} onToggle={() => setOpenEmail(openEmail === professional.email ? null : professional.email)} onReserve={onReserve} />)}</section>{!filtered.length && <Empty text="No encontramos profesionales con esa búsqueda." />}</>;
}

function ProfessionalCard({ professional, reservations, isOpen, onToggle, onReserve }) {
  const [availability, setAvailability] = useState([]); const [services, setServices] = useState([]); const [selectedService, setSelectedService] = useState(""); const [selectedDate, setSelectedDate] = useState(""); const [loading, setLoading] = useState(false); const [notice, setNotice] = useState("");
  function load() {
    const start = new Date(); const end = todayPlus(30); setLoading(true); setNotice("");
    Promise.all([request(API.freeAvailability(professional.email, isoDate(start), isoDate(end))), request(API.services(professional.id_especialidad))])
      .then(([items, availableServices]) => { setAvailability(items); setSelectedDate(items[0]?.fecha || isoDate(start)); setServices(availableServices); setSelectedService(String(availableServices[0]?.id_servicio || "")); })
      .catch((err) => { setAvailability([]); setNotice(err.status === 503 ? "En este momento no podemos confirmar qué horarios están libres. Probá de nuevo en unos minutos." : err.message); })
      .finally(() => setLoading(false));
  }
  // Al reservar, el horario deja de estar libre: se vuelve a pedir la lista.
  useEffect(() => { if (isOpen) load(); }, [isOpen, professional.email, reservations]);
  const dates = [...new Set(availability.map((item) => item.fecha))]; const slots = availability.filter((item) => item.fecha === selectedDate);
  return <article className="card professional-card"><div className="professional-header"><div className="professional-main"><div className="professional-avatar">{initials(professional)}</div><div><h3>Dr. {professional.nombre} {professional.apellido}</h3></div><span className="specialty-pill">{professional.especialidad}</span></div><button className="clock-button" title="Ver horarios" onClick={onToggle}><Icon name="clock" /></button></div>{isOpen && <div className="availability-panel">{loading ? <p className="muted">Cargando horarios...</p> : notice ? <div className="form-error">{notice} <button className="link-button" onClick={load}>Reintentar</button></div> : dates.length ? <><label className="availability-label">Elegí un servicio</label><select className="service-select" value={selectedService} onChange={(event) => setSelectedService(event.target.value)}>{services.map((service) => <option key={service.id_servicio} value={service.id_servicio}>{service.nombre}</option>)}</select><label className="availability-label day-label">Elegí un día</label><div className="date-picker">{dates.map((date) => <button key={date} className={`date-option ${date === selectedDate ? "selected" : ""}`} onClick={() => setSelectedDate(date)}>{displayDate(date)}</button>)}</div><strong>Horarios disponibles</strong><div className="time-grid">{slots.map((slot) => <button key={slot.id_disponibilidad} className="time-slot" onClick={() => onReserve(slot, Number(selectedService), professional, services.find((service) => service.id_servicio === Number(selectedService)))}>{slot.horario_inicio.slice(0, 5)}</button>)}</div></> : <p className="muted">Este profesional no tiene horarios libres en los próximos 30 días.</p>}</div>}</article>;
}

function ProfessionalHome({ user, agenda, details, setPage, onCancel }) {
  const upcoming = agenda.filter((item) => item.estado === "RESERVADO");
  return <><Hero user={user} professional setPage={setPage} /><section><div className="section-heading"><div><h2>Próximas consultas</h2><p>Consultas agendadas en tu agenda.</p></div><button className="link-button" onClick={() => setPage("schedule")}>Ver horarios →</button></div>{upcoming.length ? <div className="reservation-grid">{upcoming.map((item) => <ReservationCard key={item.id_turno} reservation={item} details={details[item.id_turno]} professional onCancel={onCancel} />)}</div> : <Empty text="No tenés consultas agendadas." action="Administrar horarios" onAction={() => setPage("schedule")} />}</section></>;
}

function Schedule({ availability, agenda, onCreate, onUpdate, onDelete }) {
  const [selectedDate, setSelectedDate] = useState(availability[0]?.fecha || isoDate(todayPlus(1))); const [editing, setEditing] = useState(null); const [form, setForm] = useState({ fecha: selectedDate, horario_inicio: "09:00", horario_fin: "17:00", duracion: "30" });
  const dates = [...new Set([...availability.map((item) => item.fecha), ...Array.from({ length: 14 }, (_, index) => isoDate(todayPlus(index + 1)))])].sort().slice(0, 14);
  const slots = availability.filter((item) => item.fecha === selectedDate); const booked = new Set(agenda.filter((item) => item.estado === "RESERVADO").map((item) => item.id_disponibilidad));
  function openNew() { setEditing(null); setForm({ fecha: selectedDate, horario_inicio: "09:00", horario_fin: "17:00", duracion: "30" }); }
  function openEdit(slot) { const [hours, minutes] = slot.horario_inicio.slice(0, 5).split(":").map(Number); const end = slot.horario_fin.slice(0, 5).split(":").map(Number); setEditing(slot); setForm({ fecha: slot.fecha, horario_inicio: slot.horario_inicio.slice(0, 5), horario_fin: slot.horario_fin.slice(0, 5), duracion: String((end[0] * 60 + end[1]) - (hours * 60 + minutes)) }); }
  function changeDate(date) { setSelectedDate(date); setEditing(null); setForm((current) => ({ ...current, fecha: date })); }
  async function submit(event) {
    event.preventDefault();
    const [startHours, startMinutes] = form.horario_inicio.split(":").map(Number);
    const start = startHours * 60 + startMinutes;
    const duration = Number(form.duracion);
    const [endHours, endMinutes] = form.horario_fin.split(":").map(Number);
    const end = endHours * 60 + endMinutes;
    // Al modificar no se muestra la hora de fin: sale de la duración.
    if (duration <= 0 || (!editing && end <= start)) {
      window.alert("La hora de fin debe ser posterior al inicio y la duración debe ser mayor a cero.");
      return;
    }
    if (editing) {
      const finish = start + duration;
      await onUpdate(editing.id_disponibilidad, { fecha: form.fecha, horario_inicio: `${form.horario_inicio}:00`, horario_fin: `${String(Math.floor(finish / 60)).padStart(2, "0")}:${String(finish % 60).padStart(2, "0")}:00` });
    } else {
      for (let cursor = start; cursor + duration <= end; cursor += duration) {
        const finish = cursor + duration;
        await onCreate({ fecha: form.fecha, horario_inicio: `${String(Math.floor(cursor / 60)).padStart(2, "0")}:${String(cursor % 60).padStart(2, "0")}:00`, horario_fin: `${String(Math.floor(finish / 60)).padStart(2, "0")}:${String(finish % 60).padStart(2, "0")}:00` });
      }
    }
    setSelectedDate(form.fecha); setEditing(null);
  }
  return <><PageHeader kicker="Tu agenda" title="Horarios" text="Seleccioná un día para revisar y administrar tus disponibilidades." /><div className="schedule-toolbar"><button className="primary-button" onClick={openNew}><Icon name="plus" size={17} /> Nuevo horario</button></div><div className="calendar-strip">{dates.map((date) => <button key={date} className={`calendar-day ${date === selectedDate ? "selected" : ""}`} onClick={() => changeDate(date)}><strong>{displayDate(date, { weekday: "short" })}</strong><span>{displayDate(date, { day: "numeric", month: "short" })}</span></button>)}</div><div className="schedule-layout"><section className="card schedule-list"><div className="section-heading"><div><h2>{displayDate(selectedDate, { weekday: "long", day: "numeric", month: "long" })}</h2><p>{slots.length} horarios disponibles</p></div></div>{slots.length ? slots.map((slot) => <div className={`schedule-row ${booked.has(slot.id_disponibilidad) ? "booked-row" : ""}`} key={slot.id_disponibilidad}><div className="schedule-time"><Icon name="clock" size={17} /><strong>{slot.horario_inicio.slice(0, 5)} - {slot.horario_fin.slice(0, 5)}</strong></div><span className={`schedule-state ${booked.has(slot.id_disponibilidad) ? "booked" : ""}`}>{booked.has(slot.id_disponibilidad) ? "Agendado" : "Libre"}</span><div className="schedule-actions"><button title="Modificar" disabled={booked.has(slot.id_disponibilidad)} onClick={() => openEdit(slot)}><Icon name="edit" size={16} /></button><button title="Eliminar" disabled={booked.has(slot.id_disponibilidad)} onClick={() => { if (window.confirm("¿Querés eliminar este horario?")) onDelete(slot.id_disponibilidad); }}><Icon name="trash" size={16} /></button></div></div>) : <Empty text="No hay horarios para este día." action="Agregar horario" onAction={openNew} />}</section>{(editing || form.fecha === selectedDate) && <form className="card schedule-form" onSubmit={submit}><h2>{editing ? "Modificar horario" : "Nuevo horario"}</h2><p className="muted">Definí el día, el rango horario y la duración de cada consulta.</p><Field label="Día" type="date" value={form.fecha} onChange={(event) => changeDate(event.target.value)} required /><Field label="Hora de inicio" type="time" value={form.horario_inicio} onChange={(event) => setForm({ ...form, horario_inicio: event.target.value })} required />{!editing && <Field label="Hora de fin" type="time" value={form.horario_fin} onChange={(event) => setForm({ ...form, horario_fin: event.target.value })} required />}<Field label="Duración (minutos)" type="number" min="1" value={form.duracion} onChange={(event) => setForm({ ...form, duracion: event.target.value })} required /><div className="form-actions"><button type="button" className="secondary-button" onClick={() => setEditing(null)}>Cancelar</button><button className="primary-button">{editing ? "Guardar cambios" : "Crear horarios"}</button></div></form>}</div></>;
}

function Notifications() { return <><PageHeader kicker="Centro de actividad" title="Notificaciones" text="Los avisos de tus turnos llegan por mail." /><div className="notification-list"><article className="card empty-state"><Icon name="bell" size={28} /><p>Cada vez que se confirma o se cancela un turno, el paciente y el profesional reciben un mail con la fecha y el horario.</p><p className="muted">En este entorno de desarrollo los mails no salen a Internet: se pueden ver en Mailpit, en <a href="http://localhost:8025" target="_blank" rel="noopener noreferrer">http://localhost:8025</a>.</p></article></div></>; }
function Profile({ user, onLogout }) { const professional = user.tipo === "PROFESIONAL"; return <><PageHeader kicker="Tu cuenta" title="Mi perfil" text={`Información asociada a tu cuenta de ${professional ? "profesional" : "paciente"}.`} /><article className="card profile-card"><div className="profile-header"><div className="profile-avatar">{initials(user)}</div><div><h2>{user.nombre} {user.apellido}</h2><p className="muted">{professional ? "Profesional" : "Paciente"}</p></div></div><div className="profile-fields"><div className="profile-field"><label>Nombre completo</label><strong>{user.nombre} {user.apellido}</strong></div><div className="profile-field"><label>Email</label><strong>{user.email}</strong></div>{!professional && <><div className="profile-field"><label>Documento</label><strong>{user.paciente?.documento || "No informado"}</strong></div><div className="profile-field"><label>Teléfono</label><strong>{user.paciente?.telefono || "No informado"}</strong></div></>}</div><button className="secondary-button danger-button" onClick={onLogout}><Icon name="logout" size={16} /> Cerrar sesión</button></article></>; }
function PageHeader({ kicker, title, text }) { return <section className="page-header"><span className="page-kicker">{kicker}</span><h1>{title}</h1><p>{text}</p></section>; }
function Empty({ text, action, onAction }) { return <div className="card empty-state"><Icon name="calendar" size={28} /><p>{text}</p>{action && <button className="secondary-button" onClick={onAction}>{action}</button>}</div>; }

function App() {
  const [user, setUser] = useState(null); const [page, setPage] = useState("home"); const [reservations, setReservations] = useState([]); const [professionals, setProfessionals] = useState([]); const [availability, setAvailability] = useState([]); const [agenda, setAgenda] = useState([]); const [details, setDetails] = useState({}); const [toast, setToast] = useState(""); const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState("");
  const professional = user?.tipo === "PROFESIONAL";
  const range = useMemo(() => ({ desde: isoDate(new Date()), hasta: isoDate(todayPlus(30)) }), []);
  useEffect(() => {
    if (!localStorage.getItem("turnos_token")) { setLoading(false); return; }
    // Cada lista se carga por separado: si un servicio no responde, el resto de la pantalla funciona.
    function load(promise, setter, message) { return promise.then(setter).catch(() => showToast(message)); }
    request(API.profile).then((profile) => {
      setUser(profile);
      if (profile.tipo === "PROFESIONAL") {
        return Promise.all([
          load(request(API.agenda(range.desde, range.hasta)), setAgenda, "No se pudo cargar la agenda. Probá de nuevo en unos minutos."),
          load(request(API.ownAvailability(range.desde, range.hasta)), setAvailability, "No se pudieron cargar tus horarios. Probá de nuevo en unos minutos."),
        ]);
      }
      return Promise.all([
        load(request(API.reservations), setReservations, "No se pudieron cargar tus reservas. Probá de nuevo en unos minutos."),
        load(request(API.professionals), setProfessionals, "No se pudo cargar la lista de profesionales. Probá de nuevo en unos minutos."),
      ]);
    }).catch((err) => {
      // Solo un token rechazado cierra la sesión; si usuarios no responde, se ofrece reintentar.
      if (err.status === 401) localStorage.removeItem("turnos_token");
      else setLoadError("No pudimos cargar tu cuenta. Probá de nuevo en unos minutos.");
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { if (!user || professional || !professionals.length) return; Promise.all(professionals.map((provider) => request(API.services(provider.id_especialidad)).then((services) => ({ provider, services })))).then((catalogs) => { const byProfessional = Object.fromEntries(catalogs.map(({ provider, services }) => [provider.email, { specialty: provider.especialidad, services }])); setDetails(Object.fromEntries(reservations.map((reservation) => { const catalog = byProfessional[reservation.email_profesional]; const service = catalog?.services.find((item) => item.id_servicio === reservation.id_servicio); return [reservation.id_turno, { specialty: catalog?.specialty, serviceName: service?.nombre }]; }))); }); }, [user, professional, professionals, reservations]);
  function logout() { localStorage.removeItem("turnos_token"); setUser(null); setPage("home"); }
  function showToast(message) { setToast(message); window.setTimeout(() => setToast(""), 3500); }
  async function refreshProfessional() { setAvailability(await request(API.ownAvailability(range.desde, range.hasta))); setAgenda(await request(API.agenda(range.desde, range.hasta))); }
  async function createAvailability(data) { try { await request(API.createAvailability, { method: "POST", body: JSON.stringify(data) }); await refreshProfessional(); showToast("Horario creado."); } catch (err) { showToast(err.message); } }
  // Modificar un horario es eliminarlo y crear otro (ADR 003). Si no se pudo
  // eliminar (por ejemplo, 409: tiene un turno reservado), no se crea el nuevo.
  async function replaceAvailability(id, data) {
    try { await request(API.deleteAvailability(id), { method: "DELETE" }); }
    catch (err) { showToast(`No se pudo modificar el horario: ${err.message}`); await refreshProfessional(); return; }
    try { await request(API.createAvailability, { method: "POST", body: JSON.stringify(data) }); showToast("Horario modificado."); }
    catch (err) { showToast(`Se eliminó el horario anterior, pero no se pudo crear el nuevo: ${err.message}`); }
    await refreshProfessional();
  }
  async function deleteAvailability(id) { try { await request(API.deleteAvailability(id), { method: "DELETE" }); await refreshProfessional(); showToast("Horario eliminado."); } catch (err) { showToast(err.message); } }
  async function cancel(id) { if (!window.confirm("¿Querés confirmar la cancelación de este turno?")) return; try { await request(API.cancel(id), { method: "POST", body: JSON.stringify({}) }); if (professional) await refreshProfessional(); else setReservations(await request(API.reservations)); showToast("Turno cancelado."); } catch (err) { showToast(err.message); } }
  async function reserve(slot, serviceId, provider, service) { try { await request(API.reserve, { method: "POST", body: JSON.stringify({ id_disponibilidad: slot.id_disponibilidad, id_servicio: serviceId }) }); const updated = await request(API.reservations); setReservations(updated); setDetails((current) => ({ ...current, [updated.find((item) => item.id_disponibilidad === slot.id_disponibilidad)?.id_turno]: { specialty: provider.especialidad, serviceName: service?.nombre } })); showToast("Turno reservado correctamente."); } catch (err) { showToast(err.message); } }
  if (loading) return <div className="login-screen"><p className="muted">Cargando tu cuenta...</p></div>;
  if (!user && loadError) return <div className="login-screen"><div className="login-card"><p className="form-error">{loadError}</p><button className="primary-button full-width" onClick={() => window.location.reload()}>Reintentar</button></div></div>;
  if (!user) return <Login onLogin={() => window.location.reload()} />;
  const content = professional ? (page === "home" ? <ProfessionalHome user={user} agenda={agenda} details={details} setPage={setPage} onCancel={cancel} /> : page === "schedule" ? <Schedule availability={availability} agenda={agenda} onCreate={createAvailability} onUpdate={replaceAvailability} onDelete={deleteAvailability} /> : page === "notifications" ? <Notifications /> : <Profile user={user} onLogout={logout} />) : (page === "home" ? <PatientHome user={user} reservations={reservations} details={details} setPage={setPage} onCancel={cancel} /> : page === "professionals" ? <PatientProfessionals professionals={professionals} reservations={reservations} onReserve={reserve} /> : page === "notifications" ? <Notifications /> : <Profile user={user} onLogout={logout} />);
  return <div className={`app-shell ${professional ? "professional-theme" : ""}`}><Sidebar page={page} setPage={setPage} professional={professional} /><div className="main-area"><Topbar user={user} page={page} setPage={setPage} onLogout={logout} /><main className="content">{content}</main><footer className="site-footer">Proyecto Sistemas Distribuidos 2026 - Juan Martín Berglavaz, María Paz Correa, Ivana Dervaric, Paolo Portugal</footer></div>{toast && <div className="toast">{toast}</div>}</div>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
