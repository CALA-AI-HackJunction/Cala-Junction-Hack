"use strict"

const byId = (id) => document.getElementById(id)
const transcript = byId("transcript")
const message = byId("message")
const send = byId("send")
const progress = byId("progress")
const banner = byId("error")
const login = byId("login")
const storageKey = "cala-app-access"
const pending = new Set(["queued", "in_progress"])
let previous = null
let active = null

function showError(text) {
  banner.textContent = text
  banner.hidden = !text
}

function addMessage(kind, text, html) {
  const article = document.createElement("article")
  article.className = kind
  const name = document.createElement("header")
  name.textContent = kind === "user" ? "You" : "Cala Research"
  const body = document.createElement("div")
  if (html) {
    // The same-origin endpoint renders Markdown with raw HTML and images disabled.
    body.innerHTML = html
  } else {
    body.textContent = text
  }
  article.append(name, body)
  transcript.append(article)
  article.scrollIntoView({ block: "nearest" })
  return article
}

async function request(path, { body, receipt, signal } = {}) {
  const headers = { Accept: "application/json" }
  if (body) headers["Content-Type"] = "application/json"
  if (receipt) headers["X-Chat-Receipt"] = receipt
  const token = sessionStorage.getItem(storageKey)
  if (token) headers.Authorization = "Bearer " + token
  const response = await fetch(path, {
    headers, signal, method: body ? "POST" : "GET", body: body && JSON.stringify(body)
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && !login.open) login.showModal()
    throw new Error(typeof result.detail === "string" ? result.detail : "The service could not respond. Try again.")
  }
  return { ...result, receipt: response.headers.get("X-Chat-Receipt") }
}

function finish() {
  active = null
  progress.hidden = true
  send.disabled = false
}

byId("access").addEventListener("click", () => login.showModal())
login.addEventListener("close", () => {
  if (login.returnValue === "save") {
    const token = byId("token").value.trim()
    if (token) sessionStorage.setItem(storageKey, token)
    else sessionStorage.removeItem(storageKey)
    showError("")
  }
  byId("token").value = ""
  login.returnValue = ""
  message.focus()
})

byId("reset").addEventListener("click", () => {
  if (active) active.abort()
  finish()
  previous = null
  transcript.replaceChildren()
  byId("welcome").hidden = false
  message.value = ""
  showError("")
  message.focus()
})

byId("chat").addEventListener("submit", async (event) => {
  event.preventDefault()
  const text = message.value.trim()
  if (!text || active) return
  const run = new AbortController()
  active = run
  send.disabled = true
  progress.hidden = false
  byId("progress-text").textContent = "Running Cala + Gemini analysis…"
  byId("elapsed").textContent = "0s"
  showError("")
  byId("welcome").hidden = true
  const userTurn = addMessage("user", text)
  message.value = ""
  const start = Date.now()
  const ticker = setInterval(() => {
    if (active === run) byId("elapsed").textContent = Math.floor((Date.now() - start) / 1000) + "s"
  }, 1000)
  let job
  try {
    job = await request("/api/jobs", {
      body: {
        message: text,
        previous_interaction_id: previous?.interaction_id,
        environment_id: previous?.environment_id
      },
      receipt: previous?.receipt,
      signal: run.signal
    })
    while (pending.has(job.status) && active === run) {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      if (active !== run) return
      job = await request("/api/jobs/" + encodeURIComponent(job.interaction_id), {
        receipt: job.receipt,
        signal: run.signal
      })
    }
    if (active !== run) return
    if (job.status !== "completed" || !job.output_text) {
      throw new Error("The agent did not return a complete answer. Try again.")
    }
    previous = job
    addMessage("answer", job.output_text, job.output_html)
  } catch (error) {
    if (active !== run) return
    showError(error.message)
    userTurn.remove()
    if (!transcript.children.length) byId("welcome").hidden = false
    if (!message.value) message.value = text
  } finally {
    clearInterval(ticker)
    if (active === run) {
      finish()
      if (!login.open) message.focus()
    }
  }
})
