const { useEffect, useMemo, useState } = React;

const API = {
  login: "/api/usuarios/login",
  register: "/api/usuarios/registro/paciente",
  profile: "/api/usuarios/yo",
  professionals: "/api/catalogo-medicos/profesionales",
  services: (specialtyId) => `/api/catalogo-medicos/especialidades/${specialtyId}/servicios`,
  availability: (email, desde, hasta) =>
    `/api/catalogo-medicos/profesionales/${encodeURIComponent(email)}/disponibilidades?desde=${desde}&hasta=${hasta}`,
  reservations: "/api/reservas/mis-turnos",
  reserve: "/api/reservas/turnos",
  cancel: (id) => `/api/reservas/turnos/${id}/cancelar`,
};

function Icon({ name, size = 20 }) {
  const paths = {
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9" /><path d="M9 20v-6h6v6" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
    calendar: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    logout: <><path d="M10 17l5-5-5-5M15 12H3M21 19V5a2 2 0 0 0-2-2h-5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function initials(user) {
  return `${user?.nombre?.[0] || ""}${user?.apellido?.[0] || ""}`.toUpperCase();
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function displayDate(value) {
  return new Intl.DateTimeFormat("es-UY", { weekday: "short", day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00`));
}

async function request(url, options = {}) {
  const token = localStorage.getItem("turnos_token");
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "No se pudo completar la solicitud.");
  }
  return response.status === 204 ? null : response.json();
}

function Login({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", contrasena: "", nombre: "", apellido: "", documento: "", telefono: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event) {
    event.preventDefault();
    setError(""); setLoading(true);
    try {
      if (mode === "register") {
        await request(API.register, { method: "POST", body: JSON.stringify(form) });
        const token = await request(API.login, { method: "POST", body: JSON.stringify({ email: form.email, contrasena: form.contrasena }) });
        localStorage.setItem("turnos_token", token.access_token);
      } else {
        const token = await request(API.login, { method: "POST", body: JSON.stringify({ email: form.email, contrasena: form.contrasena }) });
        localStorage.setItem("turnos_token", token.access_token);
      }
      onLogin();
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }
  const update = (field) => (event) => setForm({ ...form, [field]: event.target.value });
  return <main className="login-screen"><form className={`login-card ${mode === "register" ? "register-card" : ""}`} onSubmit={submit}>
    <div className="brand"><div className="brand-mark"><Icon name="calendar" size={19} /></div><strong>Turnos médicos</strong></div>
    <h1>{mode === "register" ? "Creá tu cuenta" : "Bienvenido"}</h1><p className="muted">{mode === "register" ? "Registrate como paciente para comenzar a reservar turnos." : "Ingresá para gestionar tus turnos."}</p>
    {mode === "register" && <div className="form-grid"><div className="form-field"><label htmlFor="name">Nombre</label><input id="name" required value={form.nombre} onChange={update("nombre")} /></div><div className="form-field"><label htmlFor="last-name">Apellido</label><input id="last-name" required value={form.apellido} onChange={update("apellido")} /></div></div>}
    <div className="form-field"><label htmlFor="email">Email</label><input id="email" type="email" required value={form.email} onChange={update("email")} /></div>
    <div className="form-field"><label htmlFor="password">Contraseña</label><input id="password" type="password" minLength="8" required value={form.contrasena} onChange={update("contrasena")} /></div>
    {mode === "register" && <div className="form-grid"><div className="form-field"><label htmlFor="document">Documento</label><input id="document" required value={form.documento} onChange={update("documento")} /></div><div className="form-field"><label htmlFor="phone">Teléfono <span className="muted">(opcional)</span></label><input id="phone" value={form.telefono} onChange={update("telefono")} /></div></div>}
    {error && <div className="form-error">{error}</div>}
    <button className="primary-button full-width" disabled={loading}>{loading ? (mode === "register" ? "Creando cuenta..." : "Ingresando...") : (mode === "register" ? "Crear cuenta" : "Ingresar")}</button>
    <p className="auth-switch">{mode === "register" ? "¿Ya tenés una cuenta?" : "¿Todavía no tenés una cuenta?"} <button type="button" className="link-button" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); }}>{mode === "register" ? "Ingresar" : "Registrate"}</button></p>
  </form></main>;
}

function Topbar({ user, page, setPage, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return <header className="topbar"><div className="top-actions">
    <div className="profile-wrapper"><button className="avatar-button" onClick={() => setMenuOpen(!menuOpen)}>{initials(user)}</button>
      {menuOpen && <div className="profile-menu"><p><strong>{user.nombre} {user.apellido}</strong><br /><span className="muted">{user.email}</span></p><button onClick={() => { setMenuOpen(false); setPage("profile"); }}>Ver perfil</button><button onClick={onLogout}><Icon name="logout" size={15} /> Cerrar sesión</button></div>}
    </div>
    <div className="icon-pill">
      <button className={`icon-button ${page === "home" ? "active" : ""}`} title="Inicio" onClick={() => setPage("home")}><Icon name="home" /></button>
      <button className={`icon-button ${page === "notifications" ? "active" : ""}`} title="Notificaciones" onClick={() => setPage("notifications")}><Icon name="bell" /><span className="notification-dot" /></button>
    </div>
  </div></header>;
}

function Sidebar({ page, setPage }) {
  return <aside className="sidebar"><div className="brand"><div className="brand-mark"><Icon name="calendar" size={19} /></div><strong>Turnos</strong></div>
    <nav className="nav-list">
      <button className={`nav-button ${page === "home" ? "active" : ""}`} onClick={() => setPage("home")}><Icon name="home" /><span>Inicio</span></button>
      <button className={`nav-button ${page === "professionals" ? "active" : ""}`} onClick={() => setPage("professionals")}><Icon name="users" /><span>Profesionales</span></button>
      <button className={`nav-button ${page === "notifications" ? "active" : ""}`} onClick={() => setPage("notifications")}><Icon name="bell" /><span>Notificaciones</span></button>
      <button className={`nav-button ${page === "profile" ? "active" : ""}`} onClick={() => setPage("profile")}><Icon name="user" /><span>Mi perfil</span></button>
    </nav>
  </aside>;
}

function ReservationCard({ reservation, details, onCancel }) {
  const cancelled = reservation.estado !== "RESERVADO";
  return <article className={`card reservation-card ${cancelled ? "reservation-cancelled" : ""}`}><div className="reservation-top"><div><h3>{details?.serviceName || details?.specialty || "Turno médico"}</h3><p className="muted">{details?.serviceName && details?.specialty ? `${details.specialty} · ` : ""}{reservation.horario_inicio.slice(0, 5)} - {reservation.horario_fin.slice(0, 5)}</p></div><div className="date-badge">{displayDate(reservation.fecha)}</div></div>
    <div className="reservation-top"><span className={`status ${cancelled ? "cancelled" : ""}`}>{cancelled ? "CANCELADO" : "CONFIRMADO"}</span>{!cancelled && <button className="link-button" onClick={() => onCancel(reservation.id_turno)}>Cancelar</button>}</div>
  </article>;
}

function Home({ user, reservations, reservationDetails, setPage, onCancel }) {
  return <><section className="hero"><div className="hero-copy"><span className="page-kicker">Portal del paciente</span><h1>Hola, {user.nombre}!</h1><p>Encontrá el profesional que necesitás y reservá tu próximo turno de forma rápida y sencilla.</p><button className="primary-button" onClick={() => setPage("professionals")}>Agendar nuevo turno <span aria-hidden="true">→</span></button></div><div className="hero-card"><Icon name="calendar" size={28} /><strong>Tu salud merece tiempo</strong><small>Consultá profesionales y elegí el horario que mejor te quede.</small></div></section>
    <section><div className="section-heading"><div><h2>Mis reservas</h2><p>Revisá tus próximos turnos.</p></div><button className="link-button" onClick={() => setPage("professionals")}>Nueva reserva →</button></div>
      {reservations.length ? <div className="reservation-grid">{reservations.map((item) => <ReservationCard key={item.id_turno} reservation={item} details={reservationDetails[item.id_turno]} onCancel={onCancel} />)}</div> : <div className="card empty-state"><Icon name="calendar" size={28} /><p>Aún no tenés reservas.</p><button className="secondary-button" onClick={() => setPage("professionals")}>Buscar un profesional</button></div>}
    </section></>;
}

function Professionals({ professionals, reservations, onReserve }) {
  const [query, setQuery] = useState("");
  const [openEmail, setOpenEmail] = useState(null);
  const filtered = professionals.filter((item) => `${item.nombre} ${item.apellido} ${item.especialidad}`.toLowerCase().includes(query.toLowerCase()));
  return <><section className="page-header"><span className="page-kicker">Encontrá atención</span><h1>Profesionales</h1><p>Elegí un profesional y encontrá el horario ideal para tu consulta.</p></section><div className="toolbar"><input className="search-input" placeholder="Buscar por nombre o especialidad" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
    <section className="professional-list">{filtered.map((professional) => <ProfessionalCard key={professional.email} professional={professional} reservations={reservations} isOpen={openEmail === professional.email} onToggle={() => setOpenEmail(openEmail === professional.email ? null : professional.email)} onReserve={onReserve} />)}</section>
    {!filtered.length && <div className="card empty-state">No encontramos profesionales con esa búsqueda.</div>}</>;
}

function ProfessionalCard({ professional, reservations, isOpen, onToggle, onReserve }) {
  const [availability, setAvailability] = useState([]);
  const [services, setServices] = useState([]);
  const [selectedService, setSelectedService] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!isOpen) return;
    const start = new Date(); const end = new Date(); end.setDate(end.getDate() + 30);
    setLoading(true);
    Promise.all([
      request(API.availability(professional.email, isoDate(start), isoDate(end))),
      request(API.services(professional.id_especialidad)),
    ]).then(([items, availableServices]) => {
      setAvailability(items); setSelectedDate(items[0]?.fecha || isoDate(start));
      setServices(availableServices); setSelectedService(String(availableServices[0]?.id_servicio || ""));
    }).catch(() => setAvailability([])).finally(() => setLoading(false));
  }, [isOpen, professional.email]);
  const dates = [...new Set(availability.map((item) => item.fecha))];
  const slots = availability.filter((item) => item.fecha === selectedDate);
  const booked = new Set(reservations.filter((item) => item.email_profesional === professional.email && item.estado === "RESERVADO").map((item) => item.id_disponibilidad));
  return <article className="card professional-card"><div className="professional-header"><div className="professional-main"><div className="professional-avatar">{initials(professional)}</div><div><h3>Dr. {professional.nombre} {professional.apellido}</h3></div><span className="specialty-pill">{professional.especialidad}</span></div><button className="clock-button" title="Ver horarios" onClick={onToggle}><Icon name="clock" /></button></div>
    {isOpen && <div className="availability-panel">{loading ? <p className="muted">Cargando horarios...</p> : dates.length ? <><label className="availability-label" htmlFor={`service-${professional.email}`}>Elegí un servicio</label><select id={`service-${professional.email}`} className="service-select" value={selectedService} onChange={(event) => setSelectedService(event.target.value)}>{services.map((service) => <option key={service.id_servicio} value={service.id_servicio}>{service.nombre}</option>)}</select><label className="availability-label day-label">Elegí un día</label><div className="date-picker">{dates.map((date) => <button key={date} className={`date-option ${date === selectedDate ? "selected" : ""}`} onClick={() => setSelectedDate(date)}>{displayDate(date)}</button>)}</div><strong>Horarios disponibles</strong><div className="time-grid">{slots.map((slot) => <button key={slot.id_disponibilidad} className={`time-slot ${booked.has(slot.id_disponibilidad) ? "booked" : ""}`} disabled={booked.has(slot.id_disponibilidad)} onClick={() => onReserve(slot, Number(selectedService), professional, services.find((service) => service.id_servicio === Number(selectedService)))}>{slot.horario_inicio.slice(0, 5)}</button>)}</div></> : <p className="muted">Este profesional todavía no tiene horarios publicados.</p>}</div>}
  </article>;
}

function Notifications() {
  return <><section className="page-header"><span className="page-kicker">Centro de actividad</span><h1>Notificaciones</h1><p>Acá vas a encontrar las novedades sobre tus turnos.</p></section><div className="notification-list"><div className="card empty-state"><Icon name="bell" size={28} /><p>Todavía no tenés notificaciones.</p><small>Te avisaremos cuando se confirme o cancele un turno.</small></div></div></>;
}

function Profile({ user, onLogout }) {
  return <><section className="page-header"><span className="page-kicker">Tu cuenta</span><h1>Mi perfil</h1><p>Información asociada a tu cuenta de paciente.</p></section><article className="card profile-card"><div className="profile-header"><div className="profile-avatar">{initials(user)}</div><div><h2>{user.nombre} {user.apellido}</h2><p className="muted">Paciente</p></div></div><div className="profile-fields"><div className="profile-field"><label>Nombre completo</label><strong>{user.nombre} {user.apellido}</strong></div><div className="profile-field"><label>Email</label><strong>{user.email}</strong></div><div className="profile-field"><label>Documento</label><strong>{user.paciente?.documento || "No informado"}</strong></div><div className="profile-field"><label>Teléfono</label><strong>{user.paciente?.telefono || "No informado"}</strong></div></div><button className="secondary-button danger-button" onClick={onLogout}><Icon name="logout" size={16} /> Cerrar sesión</button></article></>;
}

function App() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState("home");
  const [reservations, setReservations] = useState([]);
  const [professionals, setProfessionals] = useState([]);
  const [reservationDetails, setReservationDetails] = useState({});
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!localStorage.getItem("turnos_token")) { setLoading(false); return; }
    let loadedReservations = [];
    Promise.all([request(API.profile), request(API.reservations), request(API.professionals)]).then(([profile, ownReservations, providers]) => {
      loadedReservations = ownReservations;
      setUser(profile); setReservations(ownReservations); setProfessionals(providers);
      return Promise.all(providers.map((provider) => request(API.services(provider.id_especialidad)).then((services) => ({ provider, services }))));
    }).then((catalogs) => {
      const byProfessional = Object.fromEntries(catalogs.map(({ provider, services }) => [provider.email, { specialty: provider.especialidad, services }]));
      setReservationDetails(Object.fromEntries(loadedReservations.map((reservation) => {
        const catalog = byProfessional[reservation.email_profesional];
        const service = catalog?.services.find((item) => item.id_servicio === reservation.id_servicio);
        return [reservation.id_turno, { specialty: catalog?.specialty, serviceName: service?.nombre }];
      })));
    }).catch(() => localStorage.removeItem("turnos_token")).finally(() => setLoading(false));
  }, []);
  function logout() { localStorage.removeItem("turnos_token"); setUser(null); setPage("home"); }
  async function cancel(id) {
    if (!window.confirm("¿Querés confirmar la cancelación de este turno?")) return;
    try { await request(API.cancel(id), { method: "POST", body: JSON.stringify({}) }); setReservations(await request(API.reservations)); showToast("Reserva cancelada."); } catch (err) { showToast(err.message); }
  }
  async function reserve(slot, serviceId, professional, service) {
    try {
      await request(API.reserve, { method: "POST", body: JSON.stringify({ id_disponibilidad: slot.id_disponibilidad, id_servicio: serviceId }) });
      const updatedReservations = await request(API.reservations);
      const newReservation = updatedReservations.find((reservation) => reservation.id_disponibilidad === slot.id_disponibilidad);
      if (newReservation) setReservationDetails((current) => ({ ...current, [newReservation.id_turno]: { specialty: professional.especialidad, serviceName: service?.nombre } }));
      setReservations(updatedReservations);
      showToast("Turno reservado correctamente.");
    } catch (err) { showToast(err.message); }
  }
  function showToast(message) { setToast(message); window.setTimeout(() => setToast(""), 3500); }
  if (loading) return <div className="login-screen"><p className="muted">Cargando tu cuenta...</p></div>;
  if (!user) return <Login onLogin={() => window.location.reload()} />;
  const content = page === "home" ? <Home user={user} reservations={reservations} reservationDetails={reservationDetails} setPage={setPage} onCancel={cancel} /> : page === "professionals" ? <Professionals professionals={professionals} reservations={reservations} onReserve={reserve} /> : page === "notifications" ? <Notifications /> : <Profile user={user} onLogout={logout} />;
  return <div className="app-shell"><Sidebar page={page} setPage={setPage} /><div className="main-area"><Topbar user={user} page={page} setPage={setPage} onLogout={logout} /><main className="content">{content}</main><footer className="site-footer">Proyecto Sistemas Distribuidos 2026 - Juan Martín Berglavaz, María Paz Correa, Ivana Dervaric, Paolo Portugal</footer></div>{toast && <div className="toast">{toast}</div>}</div>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
