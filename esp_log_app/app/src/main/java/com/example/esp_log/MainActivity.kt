package com.example.esp_log

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.width
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.example.esp_log.ui.theme.Esp_logTheme
import com.hoho.android.usbserial.driver.UsbSerialDriver
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import com.hoho.android.usbserial.util.SerialInputOutputManager
import java.nio.charset.Charset

class MainActivity : ComponentActivity() {
    private val actionUsbPermission = "com.example.esp_log.USB_PERMISSION"
    private lateinit var usbManager: UsbManager
    private var driver: UsbSerialDriver? = null
    private var connection: UsbDeviceConnection? = null
    private var port: UsbSerialPort? = null
    private var ioManager: SerialInputOutputManager? = null
    private var receiverRegistered: Boolean = false
    private var partial: String = ""

    private var onLog: ((String) -> Unit)? = null
    private var onStatus: ((String) -> Unit)? = null

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == actionUsbPermission) {
                val device = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE, UsbDevice::class.java)
                val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                if (device != null && granted) openDevice()
                else onStatus?.invoke("权限拒绝")
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            Esp_logTheme {
                var status by remember { mutableStateOf("未连接") }
                var logs by remember { mutableStateOf(listOf<LogItem>()) }
                var searchQuery by remember { mutableStateOf("") }
                var searchResults by remember { mutableStateOf(listOf<Int>()) }
                var showSearch by remember { mutableStateOf(false) }
                var expandedDevices by remember { mutableStateOf(false) }
                var expandedBaud by remember { mutableStateOf(false) }
                var selectedDriverIndex by remember { mutableStateOf(-1) }
                var drivers by remember { mutableStateOf(listOf<UsbSerialDriver>()) }
                val baudRates = listOf("9600","19200","38400","57600","115200","921600")
                var baud by remember { mutableStateOf("115200") }
                var fError by remember { mutableStateOf(true) }
                var fWarning by remember { mutableStateOf(true) }
                var fInfo by remember { mutableStateOf(true) }
                var fDebug by remember { mutableStateOf(true) }
                var fVerbose by remember { mutableStateOf(true) }

                onLog = { s ->
                    val all = partial + s
                    val parts = all.split('\n')
                    partial = if (all.endsWith('\n')) "" else parts.lastOrNull() ?: ""
                    val complete = if (partial.isEmpty()) parts else parts.dropLast(1)
                    val mapped = complete.mapNotNull { mapLine(it, fError, fWarning, fInfo, fDebug, fVerbose) }
                    if (mapped.isNotEmpty()) logs = logs + mapped
                }
                onStatus = { s -> status = s }

                DisposableEffect(Unit) {
                    if (!receiverRegistered) {
                        val filter = IntentFilter(actionUsbPermission)
                        try {
                            ContextCompat.registerReceiver(
                                this@MainActivity,
                                usbReceiver,
                                filter,
                                ContextCompat.RECEIVER_NOT_EXPORTED
                            )
                            receiverRegistered = true
                        } catch (_: Exception) {
                            status = "注册USB接收器失败"
                        }
                    }
                    onDispose {
                        if (receiverRegistered) {
                            try { unregisterReceiver(usbReceiver) } catch (_: Exception) {}
                            receiverRegistered = false
                        }
                    }
                }

                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    Row(modifier = Modifier.padding(innerPadding).fillMaxSize()) {
                        Column(modifier = Modifier.weight(1f)) {
                            Row(modifier = Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Button(onClick = {
                                    drivers = refreshDrivers()
                                    selectedDriverIndex = if (drivers.isNotEmpty()) 0 else -1
                                }) { Text("刷新") }
                                Column {
                                    Button(onClick = { expandedDevices = true }) { Text(if (selectedDriverIndex>=0) driverLabel(drivers[selectedDriverIndex]) else "选择设备") }
                                    DropdownMenu(expanded = expandedDevices, onDismissRequest = { expandedDevices = false }) {
                                        drivers.forEachIndexed { idx, d ->
                                            DropdownMenuItem(text = { Text(driverLabel(d)) }, onClick = { selectedDriverIndex = idx; expandedDevices = false })
                                        }
                                    }
                                }
                                Column {
                                    Button(onClick = { expandedBaud = true }) { Text(baud) }
                                    DropdownMenu(expanded = expandedBaud, onDismissRequest = { expandedBaud = false }) {
                                        baudRates.forEach { b -> DropdownMenuItem(text = { Text(b) }, onClick = { baud = b; expandedBaud = false }) }
                                    }
                                }
                                Button(onClick = {
                                    connectWithSelection(selectedDriverIndex, drivers, baud, statusSetter = { status = it })
                                }) { Text("打开") }
                                Button(onClick = { disconnect() }) { Text("关闭") }
                                OutlinedTextField(value = searchQuery, onValueChange = { searchQuery = it }, label = { Text("查找") })
                                Button(onClick = {
                                    val q = searchQuery.trim()
                                    if (q.isNotEmpty()) {
                                        searchResults = logs.mapIndexedNotNull { i, li -> if (li.text.contains(q)) i else null }
                                        showSearch = searchResults.isNotEmpty()
                                    }
                                }) { Text("查找") }
                                Button(onClick = {
                                    logs = emptyList()
                                    searchQuery = ""
                                    showSearch = false
                                    searchResults = emptyList()
                                }) { Text("清空") }
                            }
                            Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Row { Checkbox(checked = fError, onCheckedChange = { fError = it }); Text("Error") }
                                Row { Checkbox(checked = fWarning, onCheckedChange = { fWarning = it }); Text("Warning") }
                                Row { Checkbox(checked = fInfo, onCheckedChange = { fInfo = it }); Text("Info") }
                                Row { Checkbox(checked = fDebug, onCheckedChange = { fDebug = it }); Text("Debug") }
                                Row { Checkbox(checked = fVerbose, onCheckedChange = { fVerbose = it }); Text("Verbose") }
                                Text(text = status)
                            }
                            LazyColumn(modifier = Modifier.fillMaxSize().padding(12.dp)) {
                                items(logs) { li -> Text(li.text, color = li.color) }
                            }
                        }
                        Column(modifier = Modifier.width(320.dp).padding(12.dp)) {
                            if (showSearch) {
                                Text("查找结果: ${searchQuery} (${searchResults.size}项)")
                                LazyColumn(modifier = Modifier.fillMaxSize()) {
                                    items(searchResults) { idx ->
                                        Button(onClick = { }) { Text("第${idx+1}行: ${preview(logs[idx].text)}") }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private fun connect() {
        val mgr = getSystemService(Context.USB_SERVICE) as? UsbManager ?: run {
            onStatus?.invoke("USB服务不可用")
            return
        }
        usbManager = mgr
        val drivers = UsbSerialProber.getDefaultProber().findAllDrivers(mgr)
        if (drivers.isEmpty()) {
            onStatus?.invoke("未发现设备")
            return
        }
        driver = drivers.first()
        val device = driver!!.device
        if (!mgr.hasPermission(device)) {
            val pi = PendingIntent.getBroadcast(this, 0, Intent(actionUsbPermission), PendingIntent.FLAG_IMMUTABLE)
            mgr.requestPermission(device, pi)
            onStatus?.invoke("请求权限")
            return
        }
        openDevice()
    }

    private fun openDevice() {
        if (!::usbManager.isInitialized) {
            onStatus?.invoke("USB服务未初始化")
            return
        }
        val d = driver ?: return
        connection = usbManager.openDevice(d.device)
        if (connection == null) {
            onStatus?.invoke("连接失败")
            return
        }
        port = d.ports.firstOrNull()
        if (port == null) {
            onStatus?.invoke("无可用端口")
            return
        }
        try {
            port!!.open(connection)
            port!!.setParameters(115200, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
            try {
                port!!.setDTR(true)
                port!!.setRTS(true)
                Thread.sleep(500)
                port!!.setDTR(false)
                port!!.setRTS(false)
            } catch (_: Exception) {}
            startIo()
            onStatus?.invoke("已连接")
        } catch (e: Exception) {
            onStatus?.invoke("打开失败")
        }
    }

    private fun startIo() {
        stopIo()
        val p = port ?: return
        ioManager = SerialInputOutputManager(p, object : SerialInputOutputManager.Listener {
            override fun onNewData(data: ByteArray) {
                val s = String(data, Charset.forName("UTF-8"))
                runOnUiThread { onLog?.invoke(s) }
            }
            override fun onRunError(e: Exception) {
                runOnUiThread { onStatus?.invoke("读取错误") }
            }
        })
        ioManager!!.start()
    }

    private fun stopIo() {
        ioManager?.stop()
        ioManager = null
    }

    private fun disconnect() {
        stopIo()
        try {
            port?.close()
        } catch (_: Exception) {}
        connection?.close()
        port = null
        connection = null
        driver = null
        onStatus?.invoke("已断开")
    }

    private fun refreshDrivers(): List<UsbSerialDriver> {
        val mgr = getSystemService(Context.USB_SERVICE) as? UsbManager ?: return emptyList()
        return UsbSerialProber.getDefaultProber().findAllDrivers(mgr)
    }

    private fun connectWithSelection(index: Int, drivers: List<UsbSerialDriver>, baud: String, statusSetter: (String) -> Unit) {
        if (index < 0 || index >= drivers.size) {
            statusSetter("未选择设备")
            return
        }
        driver = drivers[index]
        val mgr = getSystemService(Context.USB_SERVICE) as? UsbManager ?: run { statusSetter("USB服务不可用"); return }
        usbManager = mgr
        val device = driver!!.device
        if (!mgr.hasPermission(device)) {
            val pi = PendingIntent.getBroadcast(this, 0, Intent(actionUsbPermission), PendingIntent.FLAG_IMMUTABLE)
            mgr.requestPermission(device, pi)
            statusSetter("请求权限")
            return
        }
        try { port?.close() } catch (_: Exception) {}
        try { connection?.close() } catch (_: Exception) {}
        try {
            connection = usbManager.openDevice(device)
            port = driver!!.ports.firstOrNull()
            if (connection != null && port != null) {
                port!!.open(connection)
                val b = baud.toIntOrNull() ?: 115200
                port!!.setParameters(b, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
                startIo()
                statusSetter("已连接")
            } else {
                statusSetter("连接失败")
            }
        } catch (_: Exception) {
            statusSetter("打开失败")
        }
    }

    private fun driverLabel(d: UsbSerialDriver): String {
        val dev = d.device
        return "${dev.deviceName} VID=${dev.vendorId} PID=${dev.productId}"
    }

    private fun preview(t: String): String {
        return if (t.length > 60) t.substring(0, 60) + "…" else t
    }

    data class LogItem(val text: String, val color: Color)

    private fun mapLine(line: String, fError: Boolean, fWarning: Boolean, fInfo: Boolean, fDebug: Boolean, fVerbose: Boolean): LogItem? {
        val t = line.trim()
        if (t.isEmpty()) return null
        var c = Color.Black
        if (t.startsWith("E (")) { c = Color.Red; if (!fError) return null }
        else if (t.startsWith("W (")) { c = Color(0xFFFFA500); if (!fWarning) return null }
        else if (t.startsWith("I (")) { c = Color(0xFF2BAE85); if (!fInfo) return null }
        else if (t.startsWith("D (")) { c = Color.Blue; if (!fDebug) return null }
        else if (t.startsWith("V (")) { c = Color(0xFF800080); if (!fVerbose) return null }
        return LogItem(t, c)
    }
}