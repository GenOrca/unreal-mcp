// Copyright (c) 2025 GenOrca. All Rights Reserved.

#include "MCPythonHelper.h"

#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Editor.h"
#include "Editor/Transactor.h"
#include "HAL/FileManager.h"
#include "Misc/App.h"
#include "Misc/EngineVersion.h"
#include "Misc/PackageName.h"
#include "Misc/StringBuilder.h"
#include "Modules/ModuleManager.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

namespace
{
    TUniquePtr<FScopedTransaction> GActiveWorkflowTransaction;
    FString GActiveWorkflowTransactionId;
    int32 GActiveWorkflowTransactionIndex = INDEX_NONE;
    FGuid GActiveWorkflowTransactionGuid;
    FString GLastCommittedWorkflowTransactionId;
    int32 GLastCommittedWorkflowTransactionIndex = INDEX_NONE;
    FGuid GLastCommittedWorkflowTransactionGuid;
    const FGuid GWorkflowEditorSessionId = FGuid::NewGuid();

    const FTransaction* TransactionAtIndex(int32 TransactionIndex)
    {
        if (!GEditor || !GEditor->Trans || TransactionIndex < 0 ||
            TransactionIndex >= GEditor->Trans->GetQueueLength())
        {
            return nullptr;
        }
        return GEditor->Trans->GetTransaction(TransactionIndex);
    }

    FGuid TransactionGuidAtIndex(int32 TransactionIndex)
    {
        const FTransaction* Transaction = TransactionAtIndex(TransactionIndex);
        return Transaction
            ? Transaction->GetContext().TransactionId
            : FGuid();
    }

    bool IsCurrentWorkflowTransaction(
        int32 TransactionIndex,
        const FGuid& TransactionGuid)
    {
        if (!GEditor || !GEditor->Trans || !TransactionGuid.IsValid())
        {
            return false;
        }
        const int32 CurrentUndoIndex =
            GEditor->Trans->GetQueueLength() -
            GEditor->Trans->GetUndoCount() - 1;
        const FTransaction* Transaction =
            TransactionAtIndex(TransactionIndex);
        return CurrentUndoIndex == TransactionIndex &&
            Transaction && !Transaction->HasExpired() &&
            Transaction->GetContext().TransactionId == TransactionGuid;
    }

    FString SerializeObject(const TSharedRef<FJsonObject>& Object)
    {
        FString Result;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Result);
        FJsonSerializer::Serialize(Object, Writer);
        return Result;
    }

    FString ErrorResponse(const FString& Message, int32 TransactionIndex = INDEX_NONE)
    {
        const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), false);
        Result->SetStringField(TEXT("message"), Message);
        Result->SetNumberField(TEXT("transaction_index"), TransactionIndex);
        Result->SetBoolField(TEXT("transaction_recorded"), false);
        Result->SetBoolField(TEXT("undo_available"), false);
        Result->SetBoolField(TEXT("undo_attempted"), false);
        Result->SetBoolField(TEXT("undo_succeeded"), false);
        return SerializeObject(Result);
    }

    FString TransactionResponse(
        const FString& TransactionId,
        int32 TransactionIndex,
        bool bUndoAttempted,
        bool bUndoSucceeded,
        bool bTransactionRecorded = false,
        bool bUndoAvailable = false)
    {
        const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
        Result->SetBoolField(TEXT("success"), !bUndoAttempted || bUndoSucceeded);
        Result->SetStringField(TEXT("transaction_id"), TransactionId);
        Result->SetNumberField(TEXT("transaction_index"), TransactionIndex);
        Result->SetBoolField(TEXT("transaction_recorded"), bTransactionRecorded);
        Result->SetBoolField(TEXT("undo_available"), bUndoAvailable);
        Result->SetBoolField(TEXT("undo_attempted"), bUndoAttempted);
        Result->SetBoolField(TEXT("undo_succeeded"), bUndoSucceeded);
        if (bUndoAttempted && !bUndoSucceeded)
        {
            Result->SetStringField(TEXT("message"), TEXT("Unreal did not undo the transaction."));
        }
        return SerializeObject(Result);
    }

    FString PackageFilename(const FString& PackageName)
    {
        FString Filename = FPackageName::LongPackageNameToFilename(
            PackageName, FPackageName::GetAssetPackageExtension());
        if (!IFileManager::Get().FileExists(*Filename))
        {
            Filename = FPackageName::LongPackageNameToFilename(
                PackageName, FPackageName::GetMapPackageExtension());
        }
        return Filename;
    }
}

FString UMCPythonHelper::GetWorkflowEditorContext(const TArray<FString>& AssetPaths)
{
    const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("project_id"), FApp::GetProjectName());
    Result->SetStringField(
        TEXT("editor_session_id"),
        GWorkflowEditorSessionId.ToString(EGuidFormats::DigitsWithHyphensLower));
    Result->SetStringField(TEXT("engine_version"), FEngineVersion::Current().ToString());

    FString CurrentMap;
    if (GEditor)
    {
        if (const UWorld* World = GEditor->GetEditorWorldContext().World())
        {
            if (const UPackage* Package = World->GetOutermost())
            {
                CurrentMap = Package->GetName();
            }
        }
    }
    Result->SetStringField(TEXT("current_map"), CurrentMap);

    FAssetRegistryModule& AssetRegistryModule =
        FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
    const IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();
    const TSharedRef<FJsonObject> Fingerprints = MakeShared<FJsonObject>();

    for (const FString& AssetPath : AssetPaths)
    {
        const FString PackageName = FPackageName::ObjectPathToPackageName(AssetPath);
        const FName PackageFName(*PackageName);
        const TOptional<FAssetPackageData> PackageData =
            AssetRegistry.GetAssetPackageDataCopy(PackageFName);
        TArray<FAssetData> AssetsInPackage;
        AssetRegistry.GetAssetsByPackageName(
            PackageFName, AssetsInPackage, false);
        const TSharedRef<FJsonObject> Fingerprint = MakeShared<FJsonObject>();
        Fingerprint->SetStringField(TEXT("asset_path"), AssetPath);
        Fingerprint->SetBoolField(TEXT("exists"), !AssetsInPackage.IsEmpty());

        if (PackageData.IsSet())
        {
            TStringBuilder<40> HashBuilder;
            HashBuilder << PackageData->GetPackageSavedHash();
            Fingerprint->SetStringField(
                TEXT("package_guid"), FString(HashBuilder.ToString()));
            Fingerprint->SetNumberField(
                TEXT("disk_size"), static_cast<double>(PackageData->DiskSize));
            const FString Filename = PackageFilename(PackageName);
            if (IFileManager::Get().FileExists(*Filename))
            {
                Fingerprint->SetStringField(
                    TEXT("modified_time"),
                    IFileManager::Get().GetTimeStamp(*Filename).ToIso8601());
            }
        }

        const UPackage* LoadedPackage = FindPackage(nullptr, *PackageName);
        Fingerprint->SetBoolField(
            TEXT("dirty"), LoadedPackage && LoadedPackage->IsDirty());
        Fingerprints->SetObjectField(AssetPath, Fingerprint);
    }

    Result->SetObjectField(TEXT("asset_fingerprints"), Fingerprints);
    return SerializeObject(Result);
}

FString UMCPythonHelper::BeginWorkflowTransaction(
    const FString& TransactionId,
    const FString& Description)
{
    if (GActiveWorkflowTransaction)
    {
        return ErrorResponse(FString::Printf(
            TEXT("Transaction '%s' is already active."),
            *GActiveWorkflowTransactionId));
    }
    if (TransactionId.IsEmpty() || Description.IsEmpty())
    {
        return ErrorResponse(TEXT("Transaction id and description are required."));
    }
    if (!GEditor || !GEditor->Trans)
    {
        return ErrorResponse(TEXT("Unreal transaction buffer is unavailable."));
    }
    if (GEditor->Trans->IsActive())
    {
        return ErrorResponse(TEXT("Another Unreal transaction is already active."));
    }

    GActiveWorkflowTransaction =
        MakeUnique<FScopedTransaction>(FText::FromString(Description));
    if (!GActiveWorkflowTransaction->IsOutstanding())
    {
        GActiveWorkflowTransaction.Reset();
        return ErrorResponse(TEXT("Unreal could not begin the workflow transaction."));
    }
    GActiveWorkflowTransactionIndex = GEditor->Trans->GetQueueLength() - 1;
    GActiveWorkflowTransactionGuid =
        TransactionGuidAtIndex(GActiveWorkflowTransactionIndex);
    if (!GActiveWorkflowTransactionGuid.IsValid())
    {
        GActiveWorkflowTransaction->Cancel();
        GActiveWorkflowTransaction.Reset();
        GActiveWorkflowTransactionIndex = INDEX_NONE;
        return ErrorResponse(TEXT("Unreal did not create a workflow transaction record."));
    }
    GActiveWorkflowTransactionId = TransactionId;
    return TransactionResponse(
        TransactionId, GActiveWorkflowTransactionIndex, false, false);
}

FString UMCPythonHelper::CommitWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    const FGuid TransactionGuid = GActiveWorkflowTransactionGuid;
    GActiveWorkflowTransaction.Reset();
    GActiveWorkflowTransactionId.Empty();
    GActiveWorkflowTransactionIndex = INDEX_NONE;
    GActiveWorkflowTransactionGuid.Invalidate();
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(TransactionIndex, TransactionGuid);
    if (bTransactionRecorded)
    {
        GLastCommittedWorkflowTransactionId = TransactionId;
        GLastCommittedWorkflowTransactionIndex = TransactionIndex;
        GLastCommittedWorkflowTransactionGuid = TransactionGuid;
    }
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        false,
        false,
        bTransactionRecorded,
        bTransactionRecorded);
}

FString UMCPythonHelper::CancelWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    GActiveWorkflowTransaction->Cancel();
    GActiveWorkflowTransaction.Reset();
    GActiveWorkflowTransactionId.Empty();
    GActiveWorkflowTransactionIndex = INDEX_NONE;
    GActiveWorkflowTransactionGuid.Invalidate();
    return TransactionResponse(
        TransactionId, TransactionIndex, false, false, false, false);
}

FString UMCPythonHelper::RollbackWorkflowTransaction(const FString& TransactionId)
{
    if (!GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("No workflow transaction is active."));
    }
    if (TransactionId != GActiveWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the active transaction."));
    }
    const int32 TransactionIndex = GActiveWorkflowTransactionIndex;
    const FGuid TransactionGuid = GActiveWorkflowTransactionGuid;
    GActiveWorkflowTransaction.Reset();
    GActiveWorkflowTransactionId.Empty();
    GActiveWorkflowTransactionIndex = INDEX_NONE;
    GActiveWorkflowTransactionGuid.Invalidate();
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(TransactionIndex, TransactionGuid);
    const bool bUndoSucceeded =
        bTransactionRecorded &&
        GEditor->UndoTransaction();
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        true,
        bUndoSucceeded,
        bTransactionRecorded,
        false);
}

FString UMCPythonHelper::UndoWorkflowTransaction(const FString& TransactionId)
{
    if (GActiveWorkflowTransaction)
    {
        return ErrorResponse(TEXT("Cannot undo while a workflow transaction is active."));
    }
    if (TransactionId.IsEmpty() || TransactionId != GLastCommittedWorkflowTransactionId)
    {
        return ErrorResponse(TEXT("Transaction id does not match the last committed transaction."));
    }
    const int32 TransactionIndex = GLastCommittedWorkflowTransactionIndex;
    const bool bTransactionRecorded =
        IsCurrentWorkflowTransaction(
            TransactionIndex, GLastCommittedWorkflowTransactionGuid);
    const bool bUndoSucceeded =
        bTransactionRecorded &&
        GEditor->UndoTransaction();
    if (bUndoSucceeded)
    {
        GLastCommittedWorkflowTransactionId.Empty();
        GLastCommittedWorkflowTransactionIndex = INDEX_NONE;
        GLastCommittedWorkflowTransactionGuid.Invalidate();
    }
    return TransactionResponse(
        TransactionId,
        TransactionIndex,
        true,
        bUndoSucceeded,
        bTransactionRecorded,
        false);
}
