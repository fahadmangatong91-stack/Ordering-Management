const state = {
  token: localStorage.getItem("oms_access_token"),
  user: null,
  users: [],
  customers: [],
  products: [],
  orders: [],
  dashboard: null,
  activeView: "dashboard",
  editingProductId: null,
};

const roleLabels = {
  admin: "Admin",
  staff: "Staff",
  viewer: "Viewer",
};

const statusLabels = {
  draft: "Draft",
  confirmed: "Confirmed",
  packing: "Packing",
  shipped: "Shipped",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

const statusChoices = ["confirmed", "packing", "shipped", "delivered", "cancelled"];
const money = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" });
const dateTime = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const els = {
  loginScreen: document.querySelector("#loginScreen"),
  appShell: document.querySelector("#appShell"),
  loginForm: document.querySelector("#loginForm"),
  loginEmail: document.querySelector("#loginEmail"),
  loginPassword: document.querySelector("#loginPassword"),
  viewTitle: document.querySelector("#viewTitle"),
  viewSubtitle: document.querySelector("#viewSubtitle"),
  currentUserName: document.querySelector("#currentUserName"),
  currentUserRole: document.querySelector("#currentUserRole"),
  statsGrid: document.querySelector("#statsGrid"),
  statusList: document.querySelector("#statusList"),
  lowStockList: document.querySelector("#lowStockList"),
  recentOrdersBody: document.querySelector("#recentOrdersBody"),
  ordersBody: document.querySelector("#ordersBody"),
  productsBody: document.querySelector("#productsBody"),
  customersBody: document.querySelector("#customersBody"),
  usersBody: document.querySelector("#usersBody"),
  toast: document.querySelector("#toast"),
  orderDialog: document.querySelector("#orderDialog"),
  orderForm: document.querySelector("#orderForm"),
  orderCustomer: document.querySelector("#orderCustomer"),
  orderItems: document.querySelector("#orderItems"),
  orderSubtotal: document.querySelector("#orderSubtotal"),
  orderTax: document.querySelector("#orderTax"),
  orderTotal: document.querySelector("#orderTotal"),
};

function canManageProducts() {
  return state.user?.role === "admin";
}

function canManageUsers() {
  return state.user?.role === "admin";
}

function canManageOrders() {
  return state.user?.role === "admin" || state.user?.role === "staff";
}

function canManageCustomers() {
  return state.user?.role === "admin" || state.user?.role === "staff";
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = "Something went wrong.";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = response.statusText || message;
    }
    if (response.status === 401 && path !== "/auth/login") {
      logout(false);
      message = "Please sign in again.";
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 3200);
}

function formatMoney(value) {
  return money.format(Number(value || 0));
}

function formatDate(value) {
  return value ? dateTime.format(new Date(value)) : "";
}

function text(value) {
  const normalized = value === null || value === undefined || value === "" ? "-" : String(value);
  const escapeMap = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return normalized.replace(/[&<>"']/g, (char) => escapeMap[char]);
}

function statusPill(status) {
  const label = statusLabels[status] || status;
  return `<span class="status-pill status-${text(status)}">${text(label)}</span>`;
}

function rolePill(role) {
  return `<span class="status-pill role-${text(role)}">${text(roleLabels[role] || role)}</span>`;
}

function setView(view) {
  if (view === "users" && !canManageUsers()) {
    view = "dashboard";
  }
  state.activeView = view;
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${view}View`);
  });

  const titles = {
    dashboard: ["Dashboard", "Today's operating view"],
    orders: ["Orders", "Create, track, and advance orders"],
    inventory: ["Inventory", "Products, pricing, and stock"],
    customers: ["Customers", "Buyer records and contact details"],
    users: ["Users", "Accounts and access levels"],
  };
  els.viewTitle.textContent = titles[view][0];
  els.viewSubtitle.textContent = titles[view][1];
}

function applyRoleAccess() {
  const isAdmin = canManageUsers();
  const isStaffLevel = canManageOrders();

  document.querySelectorAll(".admin-only").forEach((element) => {
    element.classList.toggle("hidden", !isAdmin);
  });
  document.querySelectorAll(".staff-action").forEach((element) => {
    element.classList.toggle("hidden", !isStaffLevel);
  });
  document.querySelector("#productFormPanel").parentElement.classList.toggle("single-column", !canManageProducts());
  document.querySelector("#customerFormPanel").parentElement.classList.toggle("single-column", !canManageCustomers());

  els.currentUserName.textContent = state.user?.name || "";
  els.currentUserRole.textContent = roleLabels[state.user?.role] || "";

  if (!isAdmin && state.activeView === "users") {
    setView("dashboard");
  }
}

function showLogin() {
  els.loginScreen.classList.remove("hidden");
  els.appShell.classList.add("hidden");
  els.loginPassword.value = "";
}

function showApp() {
  els.loginScreen.classList.add("hidden");
  els.appShell.classList.remove("hidden");
  applyRoleAccess();
  setView(state.activeView);
}

function logout(showMessage = true) {
  state.token = null;
  state.user = null;
  state.users = [];
  state.customers = [];
  state.products = [];
  state.orders = [];
  state.dashboard = null;
  localStorage.removeItem("oms_access_token");
  showLogin();
  if (showMessage) {
    showToast("Signed out.");
  }
}

async function login(event) {
  event.preventDefault();
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: els.loginEmail.value.trim(),
        password: els.loginPassword.value,
      }),
    });
    state.token = result.access_token;
    state.user = result.user;
    localStorage.setItem("oms_access_token", state.token);
    showApp();
    await refreshAll();
    showToast(`Welcome, ${state.user.name}.`);
  } catch (error) {
    showToast(error.message);
  }
}

async function restoreSession() {
  if (!state.token) {
    showLogin();
    return;
  }
  try {
    state.user = await api("/auth/me");
    showApp();
    await refreshAll();
  } catch {
    logout(false);
  }
}

async function loadDashboard() {
  state.dashboard = await api("/dashboard");
  renderDashboard();
}

async function loadCustomers() {
  const search = document.querySelector("#customerSearch")?.value.trim();
  state.customers = await api(`/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  renderCustomers();
  renderCustomerOptions();
}

async function loadProducts() {
  const search = document.querySelector("#productSearch")?.value.trim();
  state.products = await api(`/products${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  renderProducts();
  renderOrderItems();
}

async function loadOrders() {
  const search = document.querySelector("#orderSearch").value.trim();
  const status = document.querySelector("#statusFilter").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  state.orders = await api(`/orders${params.toString() ? `?${params}` : ""}`);
  renderOrders();
}

async function loadUsers() {
  if (!canManageUsers()) {
    return;
  }
  state.users = await api("/users");
  renderUsers();
}

async function refreshAll() {
  const tasks = [loadDashboard(), loadCustomers(), loadProducts(), loadOrders()];
  if (canManageUsers()) {
    tasks.push(loadUsers());
  }
  await Promise.all(tasks);
}

function renderDashboard() {
  const summary = state.dashboard?.summary || {};
  const stats = [
    ["Total Orders", summary.total_orders || 0],
    ["Open Orders", summary.open_orders || 0],
    ["Revenue", formatMoney(summary.revenue)],
    ["Avg Order", formatMoney(summary.average_order_value)],
  ];
  els.statsGrid.innerHTML = stats
    .map(([label, value]) => `<article class="stat-card"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");

  const counts = new Map((state.dashboard?.status_counts || []).map((row) => [row.status, row.count]));
  els.statusList.innerHTML = statusChoices
    .map(
      (status) =>
        `<div class="status-row"><span>${statusPill(status)}</span><strong>${counts.get(status) || 0}</strong></div>`,
    )
    .join("");

  const lowStock = state.dashboard?.low_stock || [];
  els.lowStockList.innerHTML = lowStock.length
    ? lowStock
        .map(
          (item) =>
            `<div class="compact-row"><div><strong>${text(item.name)}</strong><div class="muted">${text(item.sku)}</div></div><strong>${item.stock_quantity}/${item.reorder_level}</strong></div>`,
        )
        .join("")
    : `<div class="empty-state">No low stock items.</div>`;

  const recent = state.dashboard?.recent_orders || [];
  els.recentOrdersBody.innerHTML = recent.length
    ? recent
        .map(
          (order) => `
            <tr>
              <td>${text(order.order_number)}</td>
              <td>${text(order.customer_name)}</td>
              <td>${statusPill(order.status)}</td>
              <td>${formatMoney(order.total)}</td>
              <td>${formatDate(order.created_at)}</td>
            </tr>`,
        )
        .join("")
    : `<tr><td colspan="5" class="empty-state">No orders yet.</td></tr>`;
}

function renderOrders() {
  els.ordersBody.innerHTML = state.orders.length
    ? state.orders
        .map((order) => {
          const locked = ["cancelled", "delivered"].includes(order.status);
          const canUpdateStatus = canManageOrders() && !locked;
          const action = canUpdateStatus
            ? `<select class="status-select" data-order-id="${order.id}">
                ${statusChoices
                  .map((status) => `<option value="${status}" ${status === order.status ? "selected" : ""}>${statusLabels[status]}</option>`)
                  .join("")}
              </select>`
            : `<span class="muted">View only</span>`;
          return `
            <tr>
              <td>${text(order.order_number)}</td>
              <td>${text(order.customer_name)}</td>
              <td>${order.item_count}</td>
              <td>${statusPill(order.status)}</td>
              <td>${formatMoney(order.total)}</td>
              <td>${formatDate(order.updated_at)}</td>
              <td>${action}</td>
            </tr>`;
        })
        .join("")
    : `<tr><td colspan="7" class="empty-state">No matching orders.</td></tr>`;
}

function renderProducts() {
  els.productsBody.innerHTML = state.products.length
    ? state.products
        .map((product) => {
          const actions = canManageProducts()
            ? `
                <button class="text-button edit-product" type="button" data-product-id="${product.id}">Edit</button>
                ${
                  product.is_active
                    ? `<button class="text-button danger-text deactivate-product" type="button" data-product-id="${product.id}">Deactivate</button>`
                    : ""
                }`
            : `<span class="muted">View only</span>`;
          return `
            <tr>
              <td>${text(product.sku)}</td>
              <td>${text(product.name)}</td>
              <td>${formatMoney(product.price)}</td>
              <td>${product.stock_quantity}</td>
              <td>${product.is_active ? "Active" : "Inactive"}</td>
              <td>${actions}</td>
            </tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="empty-state">No matching products.</td></tr>`;
}

function renderCustomers() {
  els.customersBody.innerHTML = state.customers.length
    ? state.customers
        .map(
          (customer) => `
            <tr>
              <td>${text(customer.name)}</td>
              <td>${text(customer.email)}</td>
              <td>${text(customer.phone)}</td>
              <td>${text(customer.address)}</td>
            </tr>`,
        )
        .join("")
    : `<tr><td colspan="4" class="empty-state">No matching customers.</td></tr>`;
}

function renderUsers() {
  els.usersBody.innerHTML = state.users.length
    ? state.users
        .map((user) => {
          const isCurrentUser = user.id === state.user?.id;
          const action = isCurrentUser
            ? `<span class="muted">Current user</span>`
            : `<button class="text-button toggle-user" type="button" data-user-id="${user.id}">${
                user.is_active ? "Deactivate" : "Reactivate"
              }</button>`;
          return `
            <tr>
              <td>${text(user.name)}</td>
              <td>${text(user.email)}</td>
              <td>${rolePill(user.role)}</td>
              <td>${user.is_active ? "Active" : "Inactive"}</td>
              <td>${action}</td>
            </tr>`;
        })
        .join("")
    : `<tr><td colspan="5" class="empty-state">No users yet.</td></tr>`;
}

function renderCustomerOptions() {
  els.orderCustomer.innerHTML = state.customers
    .map((customer) => `<option value="${customer.id}">${text(customer.name)}</option>`)
    .join("");
}

function activeProducts() {
  return state.products.filter((product) => product.is_active);
}

function productOptions(selectedId = "") {
  return activeProducts()
    .map(
      (product) =>
        `<option value="${product.id}" ${Number(selectedId) === product.id ? "selected" : ""}>${text(product.sku)} - ${text(product.name)} (${product.stock_quantity} available)</option>`,
    )
    .join("");
}

function orderRows() {
  return [...els.orderItems.querySelectorAll(".order-item-row")];
}

function addOrderItem(productId = "", quantity = 1) {
  const row = document.createElement("div");
  row.className = "order-item-row";
  row.innerHTML = `
    <select class="order-product" required>${productOptions(productId)}</select>
    <input class="order-quantity" type="number" min="1" step="1" value="${quantity}" required />
    <strong class="line-total">$0.00</strong>
    <button class="icon-button remove-item" type="button" aria-label="Remove item" title="Remove item">&times;</button>
  `;
  els.orderItems.append(row);
  updateOrderTotals();
}

function renderOrderItems() {
  orderRows().forEach((row) => {
    const selectedId = row.querySelector(".order-product").value;
    row.querySelector(".order-product").innerHTML = productOptions(selectedId);
  });
  if (!orderRows().length && activeProducts().length) {
    addOrderItem();
  }
  updateOrderTotals();
}

function updateOrderTotals() {
  let subtotal = 0;
  orderRows().forEach((row) => {
    const productId = Number(row.querySelector(".order-product").value);
    const quantity = Number(row.querySelector(".order-quantity").value || 0);
    const product = state.products.find((item) => item.id === productId);
    const line = product ? Number(product.price) * quantity : 0;
    row.querySelector(".line-total").textContent = formatMoney(line);
    subtotal += line;
  });
  const tax = subtotal * 0.12;
  els.orderSubtotal.textContent = formatMoney(subtotal);
  els.orderTax.textContent = formatMoney(tax);
  els.orderTotal.textContent = formatMoney(subtotal + tax);
}

function resetProductForm() {
  state.editingProductId = null;
  document.querySelector("#productFormTitle").textContent = "Add Product";
  document.querySelector("#productForm").reset();
  document.querySelector("#productId").value = "";
  document.querySelector("#productActive").checked = true;
}

function fillProductForm(product) {
  state.editingProductId = product.id;
  document.querySelector("#productFormTitle").textContent = "Edit Product";
  document.querySelector("#productId").value = product.id;
  document.querySelector("#productSku").value = product.sku;
  document.querySelector("#productName").value = product.name;
  document.querySelector("#productPrice").value = product.price;
  document.querySelector("#productStock").value = product.stock_quantity;
  document.querySelector("#productReorder").value = product.reorder_level;
  document.querySelector("#productActive").checked = product.is_active;
}

async function saveProduct(event) {
  event.preventDefault();
  const payload = {
    sku: document.querySelector("#productSku").value.trim(),
    name: document.querySelector("#productName").value.trim(),
    price: Number(document.querySelector("#productPrice").value),
    stock_quantity: Number(document.querySelector("#productStock").value),
    reorder_level: Number(document.querySelector("#productReorder").value),
  };

  try {
    if (state.editingProductId) {
      payload.is_active = document.querySelector("#productActive").checked;
      await api(`/products/${state.editingProductId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      showToast("Product updated.");
    } else {
      await api("/products", { method: "POST", body: JSON.stringify(payload) });
      showToast("Product added.");
    }
    resetProductForm();
    await Promise.all([loadProducts(), loadDashboard()]);
  } catch (error) {
    showToast(error.message);
  }
}

async function saveCustomer(event) {
  event.preventDefault();
  const payload = {
    name: document.querySelector("#customerName").value.trim(),
    email: document.querySelector("#customerEmail").value.trim() || null,
    phone: document.querySelector("#customerPhone").value.trim() || null,
    address: document.querySelector("#customerAddress").value.trim() || null,
  };

  try {
    await api("/customers", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    showToast("Customer added.");
    await loadCustomers();
  } catch (error) {
    showToast(error.message);
  }
}

async function saveUser(event) {
  event.preventDefault();
  const payload = {
    name: document.querySelector("#userName").value.trim(),
    email: document.querySelector("#userEmail").value.trim(),
    password: document.querySelector("#userPassword").value,
    role: document.querySelector("#userRole").value,
    is_active: document.querySelector("#userActive").checked,
  };

  try {
    await api("/users", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    document.querySelector("#userActive").checked = true;
    showToast("User added.");
    await loadUsers();
  } catch (error) {
    showToast(error.message);
  }
}

function openOrderDialog() {
  if (!canManageOrders()) {
    showToast("You do not have permission to create orders.");
    return;
  }
  if (!state.customers.length) {
    showToast("Add a customer before creating an order.");
    return;
  }
  if (!activeProducts().length) {
    showToast("Add an active product before creating an order.");
    return;
  }
  els.orderForm.reset();
  els.orderItems.innerHTML = "";
  renderCustomerOptions();
  addOrderItem();
  els.orderDialog.showModal();
}

function closeOrderDialog() {
  els.orderDialog.close();
}

async function createOrder(event) {
  event.preventDefault();
  const items = orderRows().map((row) => ({
    product_id: Number(row.querySelector(".order-product").value),
    quantity: Number(row.querySelector(".order-quantity").value),
  }));

  try {
    await api("/orders", {
      method: "POST",
      body: JSON.stringify({
        customer_id: Number(els.orderCustomer.value),
        items,
        tax_rate: 0.12,
        notes: document.querySelector("#orderNotes").value.trim() || null,
      }),
    });
    closeOrderDialog();
    showToast("Order created.");
    await refreshAll();
  } catch (error) {
    showToast(error.message);
  }
}

async function toggleUserActive(userId) {
  const user = state.users.find((item) => item.id === userId);
  if (!user) return;
  try {
    await api(`/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !user.is_active }),
    });
    showToast(user.is_active ? "User deactivated." : "User reactivated.");
    await loadUsers();
  } catch (error) {
    showToast(error.message);
  }
}

function bindEvents() {
  els.loginForm.addEventListener("submit", login);
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  });
  document.querySelector("#logoutButton").addEventListener("click", () => logout());
  document.querySelector("#refreshButton").addEventListener("click", () => refreshAll().then(() => showToast("Data refreshed.")));
  document.querySelector("#productForm").addEventListener("submit", saveProduct);
  document.querySelector("#customerForm").addEventListener("submit", saveCustomer);
  document.querySelector("#userForm").addEventListener("submit", saveUser);
  document.querySelector("#newOrderButton").addEventListener("click", openOrderDialog);
  document.querySelector("#closeOrderDialog").addEventListener("click", closeOrderDialog);
  document.querySelector("#cancelOrderForm").addEventListener("click", closeOrderDialog);
  document.querySelector("#addItemButton").addEventListener("click", () => addOrderItem());
  els.orderForm.addEventListener("submit", createOrder);
  els.orderItems.addEventListener("input", updateOrderTotals);
  els.orderItems.addEventListener("change", updateOrderTotals);
  els.orderItems.addEventListener("click", (event) => {
    if (!event.target.classList.contains("remove-item")) return;
    event.target.closest(".order-item-row").remove();
    if (!orderRows().length) addOrderItem();
    updateOrderTotals();
  });

  document.querySelector("#productSearch").addEventListener("input", debounce(loadProducts, 250));
  document.querySelector("#customerSearch").addEventListener("input", debounce(loadCustomers, 250));
  document.querySelector("#orderSearch").addEventListener("input", debounce(loadOrders, 250));
  document.querySelector("#statusFilter").addEventListener("change", loadOrders);
  document.querySelector("#clearProductButton").addEventListener("click", resetProductForm);

  els.productsBody.addEventListener("click", async (event) => {
    if (!canManageProducts()) return;
    const editButton = event.target.closest(".edit-product");
    const deactivateButton = event.target.closest(".deactivate-product");
    if (editButton) {
      const product = state.products.find((item) => item.id === Number(editButton.dataset.productId));
      if (product) fillProductForm(product);
    }
    if (deactivateButton) {
      const id = Number(deactivateButton.dataset.productId);
      try {
        await api(`/products/${id}`, { method: "DELETE" });
        showToast("Product deactivated.");
        await Promise.all([loadProducts(), loadDashboard()]);
      } catch (error) {
        showToast(error.message);
      }
    }
  });

  els.ordersBody.addEventListener("change", async (event) => {
    const select = event.target.closest(".status-select");
    if (!select) return;
    try {
      await api(`/orders/${select.dataset.orderId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: select.value }),
      });
      showToast("Order status updated.");
      await refreshAll();
    } catch (error) {
      showToast(error.message);
      await loadOrders();
    }
  });

  els.usersBody.addEventListener("click", (event) => {
    const toggleButton = event.target.closest(".toggle-user");
    if (!toggleButton) return;
    toggleUserActive(Number(toggleButton.dataset.userId));
  });
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

bindEvents();
restoreSession();
