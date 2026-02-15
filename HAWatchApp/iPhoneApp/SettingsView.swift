import SwiftUI
import HAWatchCore

struct iPhoneSettingsView: View {
    @State private var serverURL = ""
    @State private var accessToken = ""
    @State private var isValidating = false
    @State private var validationResult: String?
    @State private var isConnected = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Home Assistant Connection") {
                    TextField("Server URL", text: $serverURL)
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)

                    SecureField("Long-Lived Access Token", text: $accessToken)
                        .textContentType(.password)
                }

                Section {
                    Button {
                        Task { await validateAndSave() }
                    } label: {
                        HStack {
                            Text("Connect & Sync to Watch")
                            Spacer()
                            if isValidating {
                                ProgressView()
                            } else if isConnected {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    .disabled(serverURL.isEmpty || accessToken.isEmpty || isValidating)
                }

                if let result = validationResult {
                    Section {
                        Text(result)
                            .font(.callout)
                            .foregroundStyle(isConnected ? .green : .red)
                    }
                }

                if isConnected {
                    Section("Default Dashboard") {
                        NavigationLink("Choose Dashboard") {
                            DashboardPickerView(
                                serverURL: serverURL,
                                accessToken: accessToken
                            ) { dashboardId in
                                SettingsManager.shared.updateDefaultDashboard(id: dashboardId)
                            }
                        }
                    }

                    Section("Watch Complications") {
                        NavigationLink("Configure Complications") {
                            ComplicationConfigView(
                                serverURL: serverURL,
                                accessToken: accessToken
                            ) { entities in
                                SettingsManager.shared.updateComplicationEntities(entities)
                            }
                        }
                    }
                }
            }
            .navigationTitle("HA Watch")
        }
    }

    private func validateAndSave() async {
        isValidating = true
        validationResult = nil
        isConnected = false

        guard let url = URL(string: serverURL) else {
            validationResult = "Invalid URL format"
            isValidating = false
            return
        }

        let client = HAAPIClient(baseURL: url, token: accessToken)
        do {
            let config = try await client.validateConnection()
            isConnected = true
            validationResult = "Connected to \(config.locationName ?? "Home Assistant") (v\(config.version ?? "?"))"

            // Send settings to Watch via WatchConnectivity
            let settings = AppSettings(
                serverURL: serverURL,
                accessToken: accessToken
            )
            SettingsManager.shared.save(settings)
            #if canImport(WatchConnectivity)
            WatchConnectivityManager.shared.sendSettings(settings)
            #endif
        } catch {
            validationResult = "Connection failed: \(error.localizedDescription)"
        }

        isValidating = false
    }
}
