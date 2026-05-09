const MATERIAS = [
  "Arte",
  "Biologia",
  "Eletivas",
  "Filosofia",
  "Física",
  "Geografia",
  "História",
  "Inglês",
  "Matemática",
  "Português",
  "Química",
  "Sociologia",
];

function hasText(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function isMultipla(tipo) {
  const t = (tipo || "").toLowerCase();
  return t.includes("multipla") || t.includes("múltipla") || t.includes("escolha") || t.includes("objetiva");
}

function classifyQuestion(q) {
  const hasAlternativas = q.alternativas && Object.keys(q.alternativas).length > 0;
  const tipo = q.tipo || "";
  const hasEnunciado = hasText(q.enunciado_html) || hasText(q.enunciado);
  const hasResolucao = hasText(q.resolucao_html);

  if (hasAlternativas) return "alternativas";

  if ((tipo.toLowerCase().includes("aberta") || tipo.toLowerCase().includes("dissert")) && (hasEnunciado || hasResolucao)) {
    return "aberta";
  }

  if (!isMultipla(tipo) && (hasEnunciado || hasResolucao)) {
    return "aberta";
  }

  return "erro";
}

function renderRow(materia, stats) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>${materia}</td>
    <td class="right">${stats.total}</td>
    <td class="right">${stats.alternativas}</td>
    <td class="right">${stats.abertas}</td>
    <td class="right">${stats.erro}</td>
  `;
  return tr;
}

async function loadMateria(materia) {
  const file = `./por_materia/questoes_${materia}.json`;
  const resp = await fetch(encodeURI(file), { cache: "no-store" });
  if (!resp.ok) {
    throw new Error(`Falha ao carregar ${file} (${resp.status})`);
  }
  const data = await resp.json();
  const list = Array.isArray(data) ? data : (data.questoes || []);

  const stats = { total: list.length, alternativas: 0, abertas: 0, erro: 0 };
  for (const q of list) {
    const c = classifyQuestion(q);
    if (c === "alternativas") stats.alternativas += 1;
    else if (c === "aberta") stats.abertas += 1;
    else stats.erro += 1;
  }
  return stats;
}

async function main() {
  const tbody = document.getElementById("tbody");
  const status = document.getElementById("status");
  let totals = { total: 0, alternativas: 0, abertas: 0, erro: 0 };
  let loaded = 0;

  for (const materia of MATERIAS) {
    try {
      const stats = await loadMateria(materia);
      tbody.appendChild(renderRow(materia, stats));
      totals.total += stats.total;
      totals.alternativas += stats.alternativas;
      totals.abertas += stats.abertas;
      totals.erro += stats.erro;
      loaded += 1;
    } catch (e) {
      tbody.appendChild(renderRow(materia, { total: 0, alternativas: 0, abertas: 0, erro: 0 }));
      console.error(e);
    }
  }

  document.getElementById("totalEx").textContent = totals.total;
  document.getElementById("totalAlt").textContent = totals.alternativas;
  document.getElementById("totalAberta").textContent = totals.abertas;
  document.getElementById("totalErro").textContent = totals.erro;

  status.textContent = `Carregado: ${loaded}/${MATERIAS.length} matérias`;
}

main().catch((err) => {
  console.error(err);
  document.getElementById("status").textContent =
    "Erro ao carregar dados. Abra via servidor local (ex.: python3 -m http.server).";
});
