import SwiftUI
import HAWatchCore

struct ConnectionFormView: View {
    @Environment(SettingsManager.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var serverURL = ""
    @State private var accessToken = ""
    @State private var isValidating = false
    @State private var validationError: String?

    private var canConnect: Bool {
        !serverURL.isEmpty && !accessToken.isEmpty && !isValidating
    }

    var body: some View {
        Form {
            Section {
                TextField("https://homeassistant.local:8123", text: $serverURL)
                    .textContentType(.URL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
            } header: {
                Text("Server URL")
            } footer: {
                Text("Your Home Assistant server address")
            }

            Section {
                SecureField("Long-Lived Access Token", text: $accessToken)
                    .textContentType(.password)
            } footer: {
                Text("Settings \u{2192} Your Profile \u{2192} Long-Lived Access Tokens")
            }

            if let error = validationError {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                }
            }

            Section {
                Button {
                    Task { await connect() }
                } label: {
                    HStack {
                        Text("Connect")
                        Spacer()
                        if isValidating {
                            ProgressView()
                        }
                    }
                }
                .disabled(!canConnect)
            }
        }
        .navigationTitle("Connection")
        .onAppear {
            serverURL = settings.appSettings.serverURL
            accessToken = settings.appSettings.accessToken
        }
    }

    private func connect() async {
        isValidating = true
        validationError = nil

        guard let url = URL(string: serverURL) else {
            validationError = "Invalid URL format"
            isValidating = false
            return
        }

        let client = HAAPIClient(baseURL: url, token: accessToken)
        do {
            _ = try await client.validateConnection()

            let newSettings = AppSettings(
                serverURL: serverURL,
                accessToken: accessToken,
                defaultDashboardId: settings.appSettings.defaultDashboardId,
                defaultViewTitle: settings.appSettings.defaultViewTitle,
                defaultViewPath: settings.appSettings.defaultViewPath,
                complicationEntities: settings.appSettings.complicationEntities
            )
            settings.save(newSettings)

            #if canImport(WatchConnectivity)
            WatchConnectivityManager.shared.sendSettings(newSettings)
            #endif

            dismiss()
        } catch {
            validationError = error.localizedDescription
        }

        isValidating = false
    }
}
