import SwiftUI
import HAWatchCore

struct WatchSettingsView: View {
    @Environment(SettingsManager.self) private var settings
    @State private var serverURL = ""
    @State private var accessToken = ""
    @State private var isValidating = false
    @State private var validationError: String?
    @State private var isValid = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("URL", text: $serverURL)
                        .textContentType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section("Authentication") {
                    SecureField("Token", text: $accessToken)
                        .textContentType(.password)
                }

                Section {
                    Button {
                        Task { await validate() }
                    } label: {
                        HStack {
                            Text("Connect")
                            Spacer()
                            if isValidating {
                                ProgressView()
                            } else if isValid {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                            }
                        }
                    }
                    .disabled(serverURL.isEmpty || accessToken.isEmpty || isValidating)
                }

                if let error = validationError {
                    Section {
                        Text(error)
                            .font(.caption2)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                serverURL = settings.appSettings.serverURL
                accessToken = settings.appSettings.accessToken
            }
        }
    }

    private func validate() async {
        isValidating = true
        validationError = nil
        isValid = false

        guard let url = URL(string: serverURL) else {
            validationError = "Invalid URL"
            isValidating = false
            return
        }

        let client = HAAPIClient(baseURL: url, token: accessToken)
        do {
            let config = try await client.validateConnection()
            isValid = true

            // Save settings
            var appSettings = settings.appSettings
            appSettings.serverURL = serverURL
            appSettings.accessToken = accessToken
            settings.save(appSettings)

            if let name = config.locationName {
                validationError = nil
                // Successfully connected to: name
                _ = name
            }
        } catch {
            validationError = "Connection failed: \(error.localizedDescription)"
        }

        isValidating = false
    }
}
