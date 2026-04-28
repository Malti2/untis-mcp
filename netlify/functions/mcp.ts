declare const Netlify: {
  env?: { get(name: string): string | undefined };
} | undefined;

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
type RpcRequest = {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: Record<string, unknown>;
};

type Session = {
  server: string;
  school: string;
  cookie: string;
  bearer?: string;
  personId: number;
  personType: number;
  students: Array<{ personId: number; personType: number; displayName?: string }>;
};

const TOOL_DEFS = [
  {
    name: "untis_get_students",
    description: "List students linked to the WebUntis account.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "untis_get_school_info",
    description: "Fetch current school year, subjects, and time grid.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "untis_get_timetable",
    description: "Fetch timetable for a student and date range.",
    inputSchema: {
      type: "object",
      properties: {
        student_id: { type: "number" },
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "untis_get_homework",
    description: "Fetch homework assignments.",
    inputSchema: {
      type: "object",
      properties: {
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "untis_get_exams",
    description: "Fetch upcoming exams and tests.",
    inputSchema: {
      type: "object",
      properties: {
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "untis_get_absences",
    description: "Fetch student absences.",
    inputSchema: {
      type: "object",
      properties: {
        start_date: { type: "string", description: "YYYY-MM-DD" },
        end_date: { type: "string", description: "YYYY-MM-DD" },
      },
      additionalProperties: false,
    },
  },
  {
    name: "untis_get_messages",
    description: "Fetch inbox messages and notifications.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "untis_daily_report",
    description: "Generate a daily parent briefing.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "untis_raw_call",
    description: "Call a raw WebUntis JSON-RPC method.",
    inputSchema: {
      type: "object",
      properties: {
        method: { type: "string" },
        parameters: { type: "string", description: "JSON string" },
      },
      required: ["method"],
      additionalProperties: false,
    },
  },
] as const;

function env(name: string): string | undefined {
  const netlifyEnv = (globalThis as any).Netlify?.env?.get?.(name);
  if (typeof netlifyEnv === "string" && netlifyEnv.length > 0) return netlifyEnv;
  const processEnv = typeof process !== "undefined" ? process.env?.[name] : undefined;
  return typeof processEnv === "string" && processEnv.length > 0 ? processEnv : undefined;
}

const API_KEY_ENV_NAMES = ["UNTISAPIKEY", "UNTIS_API_KEY"] as const;

function normalizeAuthHeader(value: string | null): string {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) return "";
  const bearerMatch = trimmed.match(/^Bearers+(.+)$/i);
  return bearerMatch ? bearerMatch[1].trim() : trimmed;
}

function getExpectedApiKey(): string | undefined {
  for (const name of API_KEY_ENV_NAMES) {
    const value = env(name);
    if (typeof value === "string") {
      const normalized = value.normalize("NFKC").replace(/[​-‍﻿]/g, "").trim();
      if (normalized) return normalized;
    }
  }
  return undefined;
}

function logMismatch(label: string, expected: string, provided: string): void {
  const max = Math.max(expected.length, provided.length);
  for (let i = 0; i < max; i += 1) {
    if (expected[i] !== provided[i]) {
      console.log("untis-mcp auth mismatch", {
        label,
        mismatchAtIndex: i,
        expectedChar: expected[i] ?? "<eof>",
        providedChar: provided[i] ?? "<eof>",
        expectedLength: expected.length,
        providedLength: provided.length,
      });
      return;
    }
  }
  console.log("untis-mcp auth mismatch", {
    label,
    mismatchAtIndex: Math.max(expected.length, provided.length),
    expectedChar: "<eof>",
    providedChar: "<eof>",
    expectedLength: expected.length,
    providedLength: provided.length,
  });
}

function isAuthorized(req: Request): boolean {
  const expected = getExpectedApiKey();
  const xApiKey = req.headers.get("x-api-key");
  const authHeader = req.headers.get("authorization");

  console.log("untis-mcp auth debug", {
    headerKeys: Array.from(req.headers.keys()),
    hasUntisApiKey: Boolean(expected),
    xApiKeyPresent: Boolean(xApiKey),
    authorizationPresent: Boolean(authHeader),
    xApiKeyLength: xApiKey?.length ?? 0,
    authHeaderLength: authHeader?.length ?? 0,
  });

  if (!expected) return false;

  const normalizedXApiKey = xApiKey?.normalize("NFKC").replace(/[​-‍﻿]/g, "").trim();
  if (normalizedXApiKey) {
    if (normalizedXApiKey === expected) return true;
    logMismatch("x-api-key", expected, normalizedXApiKey);
  }

  if (!authHeader) return false;
  const normalizedAuth = normalizeAuthHeader(authHeader).normalize("NFKC").replace(/[​-‍﻿]/g, "").trim();
  if (normalizedAuth === expected) return true;
  if (normalizedAuth) logMismatch("authorization", expected, normalizedAuth);
  return false;
}

function unauthorizedResponse(debug: Record<string, unknown>): Response {
  return new Response(JSON.stringify({ error: "Unauthorized", debug }), {
    status: 401,
    headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" },
  });
}

function textResult(text: string, isError = false) {
  return { content: [{ type: "text", text }], ...(isError ? { isError: true } : {}) };
}

function jsonText(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function toUntisDate(isoDate: string): number {
  return Number(isoDate.replaceAll("-", ""));
}

function formatUntisDate(value: unknown): string {
  if (typeof value === "number") {
    const s = String(value);
    if (s.length === 8) return `${s.slice(6, 8)}.${s.slice(4, 6)}.${s.slice(0, 4)}`;
  }
  if (typeof value === "string") {
    const digits = value.replace(/\D/g, "");
    if (digits.length === 8) return `${digits.slice(6, 8)}.${digits.slice(4, 6)}.${digits.slice(0, 4)}`;
  }
  return String(value ?? "?");
}

function nextSchoolDay(start: Date): Date {
  const d = new Date(start);
  do {
    d.setDate(d.getDate() + 1);
  } while (d.getDay() === 0 || d.getDay() === 6);
  return d;
}

async function readJson(req: Request): Promise<RpcRequest | null> {
  const text = await req.text();
  if (!text.trim()) return null;
  return JSON.parse(text) as RpcRequest;
}

async function authenticate(): Promise<Session> {
  const server = env("WEBUNTIS_SERVER");
  const school = env("WEBUNTIS_SCHOOL");
  const user = env("WEBUNTIS_USER");
  const password = env("WEBUNTIS_PASSWORD");

  if (!server || !school || !user || !password) {
    throw new Error("Missing WebUntis environment variables: WEBUNTIS_SERVER, WEBUNTIS_SCHOOL, WEBUNTIS_USER, WEBUNTIS_PASSWORD");
  }

  const rpcUrl = `https://${server}/WebUntis/jsonrpc.do?school=${encodeURIComponent(school)}`;
  const authResp = await fetch(rpcUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      id: "1",
      method: "authenticate",
      params: { user, password, client: "untis-mcp" },
      jsonrpc: "2.0",
    }),
  });
  if (!authResp.ok) throw new Error(`WebUntis authentication failed: ${authResp.status}`);
  const authBody = await authResp.json() as any;
  if (authBody?.error) throw new Error(`WebUntis authentication error: ${authBody.error?.message ?? "unknown"}`);
  const result = authBody?.result ?? {};
  const sessionId = result.sessionId;
  if (!sessionId) throw new Error("WebUntis authentication did not return a sessionId");

  const cookie = `JSESSIONID=${sessionId}; schoolname=${school}`;
  let bearer: string | undefined;
  try {
    const tokenResp = await fetch(`https://${server}/WebUntis/api/token/new`, { headers: { cookie } });
    if (tokenResp.ok) {
      bearer = (await tokenResp.text()).trim().replace(/^"|"$/g, "");
    }
  } catch {
    bearer = undefined;
  }

  const students: Array<{ personId: number; personType: number; displayName?: string }> = [];
  if (bearer) {
    try {
      const appDataResp = await fetch(`https://${server}/WebUntis/api/rest/view/v1/app/data`, {
        headers: { cookie, authorization: `Bearer ${bearer}` },
      });
      if (appDataResp.ok) {
        const appData = await appDataResp.json() as any;
        const rawStudents = appData?.user?.students ?? [];
        for (const s of rawStudents) {
          students.push({ personId: Number(s.id), personType: 5, displayName: s.displayName });
        }
      }
    } catch {
      // ignore
    }
  }

  return {
    server,
    school,
    cookie,
    bearer,
    personId: Number(result.personId ?? 0),
    personType: Number(result.personType ?? 5),
    students,
  };
}

async function rpc(session: Session, method: string, params: Record<string, unknown> = {}): Promise<any> {
  const resp = await fetch(`https://${session.server}/WebUntis/jsonrpc.do?school=${encodeURIComponent(session.school)}`, {
    method: "POST",
    headers: { "content-type": "application/json", cookie: session.cookie },
    body: JSON.stringify({ id: "1", method, params, jsonrpc: "2.0" }),
  });
  if (!resp.ok) throw new Error(`WebUntis RPC ${method} failed: ${resp.status}`);
  const body = await resp.json() as any;
  if (body?.error) throw new Error(`WebUntis RPC error ${body.error.code}: ${body.error.message}`);
  return body?.result;
}

async function restGet(session: Session, path: string, query?: Record<string, string | number | undefined>): Promise<any> {
  const url = new URL(`https://${session.server}/WebUntis${path}`);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = { cookie: session.cookie };
  if (session.bearer) headers.authorization = `Bearer ${session.bearer}`;
  let resp = await fetch(url, { headers });
  if (resp.status === 401) {
    throw new Error(`Unauthorized while fetching ${path}`);
  }
  if (!resp.ok) throw new Error(`WebUntis GET ${path} failed: ${resp.status}`);
  return await resp.json();
}

async function getStudents(session: Session) {
  if (session.students.length) return session.students;
  return [{ personId: session.personId, personType: session.personType }];
}

async function getTimetableEnriched(session: Session, studentId: number, studentType: number, start: string, end: string) {
  try {
    const data = await restGet(session, "/api/public/timetable/weekly/data", {
      elementType: studentType,
      elementId: studentId,
      date: start,
    });
    const result = data?.data?.result?.data ?? {};
    const elementsList = Array.isArray(result.elements) ? result.elements : [];
    const elemLookup = new Map<string, any>();
    for (const e of elementsList) elemLookup.set(`${e.type}:${e.id}`, e);
    const periods: any[] = [];
    const startInt = toUntisDate(start);
    const endInt = toUntisDate(end);
    const periodDict = result.elementPeriods ?? {};
    for (const list of Object.values(periodDict) as any[]) {
      for (const p of list as any[]) {
        const pDate = Number(p?.date ?? 0);
        if (pDate < startInt || pDate > endInt) continue;
        const su: any[] = [], te: any[] = [], ro: any[] = [], kl: any[] = [];
        for (const ref of p?.elements ?? []) {
          const elem = elemLookup.get(`${ref.type}:${ref.id}`) ?? {};
          const entry = { id: ref.id, name: elem.name ?? "?", longName: elem.longName ?? "" };
          if (ref.type === 3) su.push(entry);
          else if (ref.type === 2) te.push(entry);
          else if (ref.type === 4) ro.push(entry);
          else if (ref.type === 1) kl.push(entry);
        }
        periods.push({
          id: p?.id,
          date: pDate,
          startTime: p?.startTime,
          endTime: p?.endTime,
          su,
          te,
          ro,
          kl,
          lessonCode: p?.lessonCode ?? "",
          substText: p?.substText ?? "",
          lstext: p?.lessonText ?? "",
          activityType: p?.activityType ?? "",
          code: p?.code ?? "",
        });
      }
    }
    periods.sort((a, b) => (a.date - b.date) || (a.startTime - b.startTime));
    return { periods, elements: Object.fromEntries(elemLookup) };
  } catch {
    const lessons = await rpc(session, "getTimetable", {
      id: studentId,
      type: studentType,
      startDate: toUntisDate(start),
      endDate: toUntisDate(end),
    });
    return { periods: Array.isArray(lessons) ? lessons : [], elements: {} };
  }
}

function formatDailyReport(studentId: number, timetable: any[], substitutions: any[], homework: any, exams: any, absences: any, messages: any, tomorrow: Date) {
  const wd = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"][tomorrow.getDay()];
  const tomStr = `${String(tomorrow.getDate()).padStart(2, "0")}.${String(tomorrow.getMonth() + 1).padStart(2, "0")}.${tomorrow.getFullYear()}`;
  const tomDateInt = Number(`${tomorrow.getFullYear()}${String(tomorrow.getMonth() + 1).padStart(2, "0")}${String(tomorrow.getDate()).padStart(2, "0")}`);

  const tomLessons = timetable.filter((l) => Number(l.date ?? 0) === tomDateInt).sort((a, b) => (a.startTime ?? 0) - (b.startTime ?? 0));
  const subLookup = new Map<string, any>();
  for (const sub of substitutions ?? []) subLookup.set(`${sub.date ?? 0}:${sub.startTime ?? 0}`, sub);

  const hwList = Array.isArray(homework?.data?.homeworks) ? homework.data.homeworks : Array.isArray(homework) ? homework : [];
  const examList = Array.isArray(exams?.data?.exams) ? exams.data.exams : Array.isArray(exams) ? exams : [];
  const absList = Array.isArray(absences?.data?.absences) ? absences.data.absences : Array.isArray(absences) ? absences : [];
  const msgList = Array.isArray(messages?.data?.messages) ? messages.data.messages : Array.isArray(messages) ? messages : [];
  const unread = msgList.filter((m: any) => !m?.isRead);

  const lines: string[] = [];
  lines.push(`## Schueler (ID ${studentId})`);
  lines.push("");
  const summary: string[] = [];
  if (tomLessons.length) {
    const seen = new Set<string>();
    const subjNames = tomLessons.map((l) => l?.su?.[0]?.name ?? "?").filter((s) => !seen.has(s) && seen.add(s));
    summary.push(`Stundenplan ${wd}: ${subjNames.join(", ") || "?"}`);
  } else {
    summary.push(`**Kein Unterricht** am ${wd}`);
  }
  if (examList.length) summary.push(`**${examList.length} Klausur${examList.length === 1 ? "" : "en"} diese Woche**`);
  summary.push(hwList.length ? `**${hwList.length} Hausaufgaben** eingetragen` : "Keine Hausaufgaben eingetragen");
  if (unread.length) summary.push(`**${unread.length} ungelesene Nachricht${unread.length === 1 ? "" : "en"}**`);
  const unexcused = absList.filter((a: any) => !a?.isExcused);
  if (unexcused.length) summary.push(`Fehlzeiten: ${unexcused.length} unentschuldigte Eintraege`);

  lines.push("### Auf einen Blick");
  for (const s of summary) lines.push(`- ${s}`);
  lines.push("");
  lines.push(`### Neue Nachrichten (${unread.length})`);
  if (unread.length) {
    for (const m of unread) lines.push(`- **${m.subject ?? m.title ?? "?"}**`);
  } else {
    lines.push("- Keine ungelesenen Nachrichten");
  }
  lines.push("");
  lines.push(`### Stundenplan ${wd} ${tomStr}`);
  if (tomLessons.length) {
    let period = 0;
    for (const lesson of tomLessons) {
      period += 1;
      const subj = lesson?.su?.[0]?.name ?? "?";
      const teacher = lesson?.te?.[0]?.name ?? "";
      const room = lesson?.ro?.[0]?.name ?? "";
      const sub = subLookup.get(`${lesson.date ?? 0}:${lesson.startTime ?? 0}`);
      const teacherStr = teacher ? ` (${teacher})` : "";
      const roomStr = room ? `, Raum ${room}` : "";
      if (sub?.type === "cancel") lines.push(`- **${period}. Stunde**: ~~${subj}~~ -- Entfall`);
      else if (sub) lines.push(`- **${period}. Stunde**: ${subj}${teacherStr}${roomStr} (Vertretung)`);
      else lines.push(`- **${period}. Stunde**: ${subj}${teacherStr}${roomStr}`);
    }
  } else {
    lines.push("- Kein Unterricht");
  }
  lines.push("");
  lines.push("### Klausuren & Tests (naechste 7 Tage)");
  if (examList.length) {
    for (const ex of examList) lines.push(`- **${formatUntisDate(ex.examDate ?? ex.date ?? "?")}**: ${ex.subject ?? ex.name ?? "?"} (${ex.examType ?? "Test"})`);
  } else {
    lines.push("- Keine anstehenden Arbeiten");
  }
  lines.push("");
  lines.push("### Hausaufgaben (naechste 7 Tage)");
  if (hwList.length) {
    for (const h of hwList) {
      const subj = h.subject ?? h.lessonSubject ?? "?";
      const text = h.text ?? h.description ?? "";
      const due = h.dueDate ? ` (bis ${formatUntisDate(h.dueDate)})` : "";
      lines.push(`- **${subj}**: ${text}${due}`);
    }
  } else {
    lines.push("- Keine Hausaufgaben eingetragen");
  }
  lines.push("");
  lines.push("### Fehlzeiten");
  if (absList.length) {
    for (const a of absList) lines.push(`- ${formatUntisDate(a.date ?? a.startDate ?? "?")}: ${a.isExcused ? "entschuldigt" : "unentschuldigt"}`);
  } else {
    lines.push("- Keine Fehlzeiten");
  }
  lines.push("");
  return lines.join("\n");
}

async function callTool(name: string, args: Record<string, unknown> | undefined): Promise<{ content: { type: string; text: string }[]; isError?: boolean }> {
  try {
    const session = await authenticate();
    const params = args ?? {};
    switch (name) {
      case "untis_get_students": {
        return { content: [{ type: "text", text: jsonText(await getStudents(session)) }] };
      }
      case "untis_get_school_info": {
        const schoolyear = await rpc(session, "getCurrentSchoolyear");
        const subjects = await rpc(session, "getSubjects");
        const timegrid = await rpc(session, "getTimegridUnits");
        return { content: [{ type: "text", text: jsonText({ schoolyear, subjects, timegrid }) }] };
      }
      case "untis_get_timetable": {
        const studentId = Number(params.student_id ?? session.personId);
        const studentType = session.students.length ? 5 : session.personType;
        const start = typeof params.start_date === "string" ? params.start_date : new Date().toISOString().slice(0, 10);
        const end = typeof params.end_date === "string" ? params.end_date : new Date(Date.parse(start) + 6 * 86400000).toISOString().slice(0, 10);
        const data = await getTimetableEnriched(session, studentId, studentType, start, end);
        const substitutions = await rpc(session, "getSubstitutions", { startDate: toUntisDate(start), endDate: toUntisDate(end), departmentId: 0 });
        return { content: [{ type: "text", text: jsonText({ timetable: data.periods, substitutions }) }] };
      }
      case "untis_get_homework": {
        const start = typeof params.start_date === "string" ? params.start_date : new Date().toISOString().slice(0, 10);
        const end = typeof params.end_date === "string" ? params.end_date : new Date(Date.parse(start) + 7 * 86400000).toISOString().slice(0, 10);
        return { content: [{ type: "text", text: jsonText(await restGet(session, "/api/homeworks/lessons", { startDate: toUntisDate(start), endDate: toUntisDate(end) })) }] };
      }
      case "untis_get_exams": {
        const start = typeof params.start_date === "string" ? params.start_date : new Date().toISOString().slice(0, 10);
        const end = typeof params.end_date === "string" ? params.end_date : new Date(Date.parse(start) + 30 * 86400000).toISOString().slice(0, 10);
        return { content: [{ type: "text", text: jsonText(await restGet(session, "/api/exams", { startDate: toUntisDate(start), endDate: toUntisDate(end) })) }] };
      }
      case "untis_get_absences": {
        const start = typeof params.start_date === "string" ? params.start_date : new Date().toISOString().slice(0, 10);
        const end = typeof params.end_date === "string" ? params.end_date : new Date(Date.parse(start) + 30 * 86400000).toISOString().slice(0, 10);
        return { content: [{ type: "text", text: jsonText(await restGet(session, "/api/classreg/absences/students", { startDate: toUntisDate(start), endDate: toUntisDate(end) })) }] };
      }
      case "untis_get_messages": {
        return { content: [{ type: "text", text: jsonText(await restGet(session, "/api/rest/view/v1/messages")) }] };
      }
      case "untis_daily_report": {
        const today = new Date();
        const tomorrow = nextSchoolDay(today);
        const start = today.toISOString().slice(0, 10);
        const examEnd = new Date(today.getTime() + 7 * 86400000).toISOString().slice(0, 10);
        const studentId = session.students[0]?.personId ?? session.personId;
        const studentType = session.students.length ? 5 : session.personType;
        const timetable = (await getTimetableEnriched(session, studentId, studentType, tomorrow.toISOString().slice(0, 10), tomorrow.toISOString().slice(0, 10))).periods;
        const substitutions = await rpc(session, "getSubstitutions", { startDate: toUntisDate(tomorrow.toISOString().slice(0, 10)), endDate: toUntisDate(tomorrow.toISOString().slice(0, 10)), departmentId: 0 });
        let homework = {}; let exams = {}; let absences = {}; let messages = {};
        try { homework = await restGet(session, "/api/homeworks/lessons", { startDate: toUntisDate(start), endDate: toUntisDate(examEnd) }); } catch {}
        try { exams = await restGet(session, "/api/exams", { startDate: toUntisDate(start), endDate: toUntisDate(examEnd) }); } catch {}
        try { absences = await restGet(session, "/api/classreg/absences/students", { startDate: toUntisDate(start), endDate: toUntisDate(examEnd) }); } catch {}
        try { messages = await restGet(session, "/api/rest/view/v1/messages"); } catch {}
        return { content: [{ type: "text", text: `# Eltern-Briefing (${formatUntisDate(toUntisDate(start))})\n\n${formatDailyReport(studentId, timetable, substitutions ?? [], homework, exams, absences, messages, tomorrow)}` }] };
      }
      case "untis_raw_call": {
        const method = String(params.method ?? "");
        if (!method) throw new Error("Missing method");
        const parsedParams = typeof params.parameters === "string" && params.parameters.trim() ? JSON.parse(params.parameters) : {};
        const result = await rpc(session, method, parsedParams);
        return { content: [{ type: "text", text: jsonText(result) }] };
      }
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return { content: [{ type: "text", text: error instanceof Error ? error.message : String(error) }], isError: true };
  }
}

async function handleRpc(req: Request): Promise<Response> {
  const body = await readJson(req);
  if (!body) return new Response(JSON.stringify({ jsonrpc: "2.0", error: { code: -32600, message: "Invalid Request" }, id: null }), { status: 400, headers: { "content-type": "application/json" } });

  const { id, method, params } = body;
  if (!method) {
    return new Response(JSON.stringify({ jsonrpc: "2.0", error: { code: -32600, message: "Missing method" }, id: id ?? null }), { status: 400, headers: { "content-type": "application/json" } });
  }

  if (id === undefined || id === null) {
    return new Response(null, { status: 204 });
  }

  try {
    if (method === "initialize") {
      return new Response(JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          serverInfo: { name: "untis-mcp", version: "0.1.0" },
          capabilities: { tools: {} },
        },
      }), { headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
    }
    if (method === "tools/list") {
      return new Response(JSON.stringify({ jsonrpc: "2.0", id, result: { tools: TOOL_DEFS } }), { headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
    }
    if (method === "tools/call") {
      const name = String((params as any)?.name ?? "");
      const args = ((params as any)?.arguments ?? {}) as Record<string, unknown>;
      const result = await callTool(name, args);
      return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), { headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
    }
    if (method === "ping") {
      return new Response(JSON.stringify({ jsonrpc: "2.0", id, result: {} }), { headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
    }
    return new Response(JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } }), { status: 404, headers: { "content-type": "application/json" } });
  } catch (error) {
    return new Response(JSON.stringify({
      jsonrpc: "2.0",
      id,
      error: { code: -32000, message: error instanceof Error ? error.message : String(error) },
    }), { status: 500, headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
  }
}

export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);

  if (req.method === "GET" && url.pathname === "/api/mcp") {
    return new Response(JSON.stringify({ ok: true, endpoint: "/api/mcp", authRequired: false }), {
      headers: { "content-type": "application/json", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" },
    });
  }

  const xApiKey = req.headers.get("x-api-key");
  const authHeader = req.headers.get("authorization");
  const expectedApiKey = getExpectedApiKey();
  const authorized = isAuthorized(req);
  if (!authorized) {
    return unauthorizedResponse({
      reason: "missing or mismatched API key",
      hasUntisApiKey: Boolean(expectedApiKey),
      xApiKeyPresent: Boolean(xApiKey),
      authorizationPresent: Boolean(authHeader),
      xApiKeyLength: xApiKey?.length ?? 0,
      authHeaderLength: authHeader?.length ?? 0,
    });
  }
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { allow: "GET, POST", "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
  }
  if (url.pathname !== "/api/mcp") {
    return new Response("Not Found", { status: 404, headers: { "cache-control": "no-store, max-age=0", "vary": "x-api-key, authorization" } });
  }
  return handleRpc(req);
}

export const config = { path: "/api/mcp" };

// cache-bust
