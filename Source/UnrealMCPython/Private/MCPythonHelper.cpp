// Copyright (c) 2025 GenOrca (by zenoengine). All Rights Reserved.

#include "MCPythonHelper.h"
#include "WidgetBlueprint.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "Components/PanelWidget.h"
#include "Editor.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Toolkits/AssetEditorToolkit.h"
#include "BlueprintEditor.h"
#include "BehaviorTree/BehaviorTree.h"
#include "BehaviorTree/BlackboardData.h"
#include "BehaviorTree/BTCompositeNode.h"
#include "BehaviorTree/BTTaskNode.h"
#include "BehaviorTree/BTDecorator.h"
#include "BehaviorTree/BTService.h"
#include "BehaviorTreeEditor.h"
#include "BehaviorTreeGraphNode.h"
#include "BehaviorTreeGraph.h"
#include "BehaviorTreeGraphNode_Root.h"
#include "BehaviorTreeGraphNode_Composite.h"
#include "BehaviorTreeGraphNode_Task.h"
#include "BehaviorTreeGraphNode_Decorator.h"
#include "BehaviorTreeGraphNode_Service.h"
#include "BehaviorTreeGraphNode_SimpleParallel.h"
#include "BehaviorTreeGraphNode_SubtreeTask.h"
#include "EdGraphSchema_BehaviorTree.h"
#include "EdGraph/EdGraph.h"
#include "UObject/UObjectIterator.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
// Blueprint graph includes
#include "K2Node_Event.h"
#include "K2Node_CustomEvent.h"
#include "K2Node_CallFunction.h"
#include "K2Node_IfThenElse.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_VariableGet.h"
#include "K2Node_VariableSet.h"
#include "K2Node_MacroInstance.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Engine/Blueprint.h"

TArray<UObject*> UMCPythonHelper::GetAllEditedAssets()
{
    if (!GEditor) return {};
    return GEditor->GetEditorSubsystem<UAssetEditorSubsystem>()->GetAllEditedAssets();
}

TArray<UObject*> UMCPythonHelper::GetSelectedBlueprintNodes()
{
    TArray<UObject*> Result;
    if (!GEditor) return Result;
    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        IAssetEditorInstance* AssetEditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* AssetEditorToolkit = static_cast<FAssetEditorToolkit*>(AssetEditorInstance);
        if (!AssetEditorToolkit) continue;
        TSharedPtr<SDockTab> Tab = AssetEditorToolkit->GetTabManager()->GetOwnerTab();
        if (Tab.IsValid() && Tab->IsForeground())
        {
            FBlueprintEditor* BlueprintEditor = static_cast<FBlueprintEditor*>(AssetEditorToolkit);
            if (BlueprintEditor)
            {
                FGraphPanelSelectionSet SelectedNodes = BlueprintEditor->GetSelectedNodes();
                for (UObject* Node : SelectedNodes)
                {
                    Result.Add(Node);
                }
            }
        }
    }
    return Result;
}

TArray<FMCPythonBlueprintNodeInfo> UMCPythonHelper::GetSelectedBlueprintNodeInfos()
{
    TArray<FMCPythonBlueprintNodeInfo> Result;
    if (!GEditor) return Result;
    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        IAssetEditorInstance* AssetEditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* AssetEditorToolkit = static_cast<FAssetEditorToolkit*>(AssetEditorInstance);
        if (!AssetEditorToolkit) continue;
        TSharedPtr<SDockTab> Tab = AssetEditorToolkit->GetTabManager()->GetOwnerTab();
        if (Tab.IsValid() && Tab->IsForeground())
        {
            FBlueprintEditor* BlueprintEditor = static_cast<FBlueprintEditor*>(AssetEditorToolkit);
            if (BlueprintEditor)
            {
                FGraphPanelSelectionSet SelectedNodes = BlueprintEditor->GetSelectedNodes();
                for (UObject* NodeObj : SelectedNodes)
                {
                    UEdGraphNode* Node = Cast<UEdGraphNode>(NodeObj);
                    if (!Node) continue;
                    FMCPythonBlueprintNodeInfo NodeInfo;
                    NodeInfo.NodeName = Node->GetName();
                    NodeInfo.NodeTitle = Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
                    NodeInfo.NodeComment = Node->NodeComment;
                    for (UEdGraphPin* Pin : Node->Pins)
                    {
                        if (!Pin || Pin->bHidden) continue;
                        FMCPythonBlueprintPinInfo PinInfo;
                        FString Friendly = Pin->PinFriendlyName.ToString();
                        PinInfo.PinName = Pin->GetName();
                        PinInfo.FriendlyName = Friendly;
                        PinInfo.Direction = (Pin->Direction == EGPD_Input) ? TEXT("In") : TEXT("Out");
                        PinInfo.PinType = Pin->PinType.PinCategory.ToString();
                        if (Pin->PinType.PinSubCategoryObject.IsValid())
                        {
                            PinInfo.PinSubType = Pin->PinType.PinSubCategoryObject->GetName();
                        }
                        PinInfo.DefaultValue = Pin->DefaultValue;
                        for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
                        {
                            if (LinkedPin && LinkedPin->GetOwningNode())
                            {
                                FMCPythonPinLinkInfo LinkInfo;
                                LinkInfo.NodeName = LinkedPin->GetOwningNode()->GetName();
                                LinkInfo.NodeTitle = LinkedPin->GetOwningNode()->GetNodeTitle(ENodeTitleType::FullTitle).ToString();
                                FString LinkedFriendly = LinkedPin->PinFriendlyName.ToString();
                                LinkInfo.PinName = LinkedFriendly.IsEmpty() ? LinkedPin->GetName() : LinkedFriendly;
                                PinInfo.LinkedTo.Add(LinkInfo);
                            }
                        }
                        NodeInfo.Pins.Add(PinInfo);
                    }
                    Result.Add(NodeInfo);
                }
            }
        }
    }
    return Result;
}

// ─── Behavior Tree Helpers (internal) ────────────────────────────────────────

static FMCPythonBTNodeInfo SerializeBTNode(UBTCompositeNode* Node)
{
    FMCPythonBTNodeInfo Info;
    if (!Node) return Info;

    Info.NodeName = Node->GetNodeName();
    Info.NodeClass = Node->GetClass()->GetName();

    // Services on this composite node
    for (UBTService* Svc : Node->Services)
    {
        if (Svc)
        {
            Info.ServiceClasses.Add(Svc->GetClass()->GetName());
            Info.ServiceNames.Add(Svc->GetNodeName());
        }
    }

    // Children
    for (const FBTCompositeChild& Child : Node->Children)
    {
        if (Child.ChildComposite)
        {
            FMCPythonBTNodeInfo ChildInfo = SerializeBTNode(Child.ChildComposite);
            // Decorators are stored per-child-connection
            for (UBTDecorator* Dec : Child.Decorators)
            {
                if (Dec)
                {
                    ChildInfo.DecoratorClasses.Add(Dec->GetClass()->GetName());
                    ChildInfo.DecoratorNames.Add(Dec->GetNodeName());
                }
            }
            Info.Children.Add(ChildInfo);
        }
        else if (Child.ChildTask)
        {
            FMCPythonBTNodeInfo TaskInfo;
            TaskInfo.NodeName = Child.ChildTask->GetNodeName();
            TaskInfo.NodeClass = Child.ChildTask->GetClass()->GetName();

            // Decorators on this child connection
            for (UBTDecorator* Dec : Child.Decorators)
            {
                if (Dec)
                {
                    TaskInfo.DecoratorClasses.Add(Dec->GetClass()->GetName());
                    TaskInfo.DecoratorNames.Add(Dec->GetNodeName());
                }
            }

            // Services on task node
            for (UBTService* Svc : Child.ChildTask->Services)
            {
                if (Svc)
                {
                    TaskInfo.ServiceClasses.Add(Svc->GetClass()->GetName());
                    TaskInfo.ServiceNames.Add(Svc->GetNodeName());
                }
            }

            Info.Children.Add(TaskInfo);
        }
    }

    return Info;
}

static UBTNode* FindNodeByName(UBTCompositeNode* Root, const FString& Name)
{
    if (!Root) return nullptr;

    // Check root itself
    if (Root->GetNodeName() == Name || Root->GetName() == Name)
        return Root;

    // Check root's services
    for (UBTService* Svc : Root->Services)
    {
        if (Svc && (Svc->GetNodeName() == Name || Svc->GetName() == Name))
            return Svc;
    }

    // Check children
    for (const FBTCompositeChild& Child : Root->Children)
    {
        // Check decorators on this child
        for (UBTDecorator* Dec : Child.Decorators)
        {
            if (Dec && (Dec->GetNodeName() == Name || Dec->GetName() == Name))
                return Dec;
        }

        if (Child.ChildComposite)
        {
            UBTNode* Found = FindNodeByName(Child.ChildComposite, Name);
            if (Found) return Found;
        }
        else if (Child.ChildTask)
        {
            if (Child.ChildTask->GetNodeName() == Name || Child.ChildTask->GetName() == Name)
                return Child.ChildTask;

            // Check task's services
            for (UBTService* Svc : Child.ChildTask->Services)
            {
                if (Svc && (Svc->GetNodeName() == Name || Svc->GetName() == Name))
                    return Svc;
            }
        }
    }

    return nullptr;
}

// ─── JSON serialization for BT tree ─────────────────────────────────────────

static TSharedPtr<FJsonObject> BTNodeInfoToJson(const FMCPythonBTNodeInfo& Info)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetStringField(TEXT("node_name"), Info.NodeName);
    Obj->SetStringField(TEXT("node_class"), Info.NodeClass);

    if (Info.DecoratorClasses.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> DecArr;
        for (int32 i = 0; i < Info.DecoratorClasses.Num(); ++i)
        {
            TSharedPtr<FJsonObject> DecObj = MakeShareable(new FJsonObject());
            DecObj->SetStringField(TEXT("class"), Info.DecoratorClasses[i]);
            if (Info.DecoratorNames.IsValidIndex(i))
                DecObj->SetStringField(TEXT("name"), Info.DecoratorNames[i]);
            DecArr.Add(MakeShareable(new FJsonValueObject(DecObj)));
        }
        Obj->SetArrayField(TEXT("decorators"), DecArr);
    }

    if (Info.ServiceClasses.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> SvcArr;
        for (int32 i = 0; i < Info.ServiceClasses.Num(); ++i)
        {
            TSharedPtr<FJsonObject> SvcObj = MakeShareable(new FJsonObject());
            SvcObj->SetStringField(TEXT("class"), Info.ServiceClasses[i]);
            if (Info.ServiceNames.IsValidIndex(i))
                SvcObj->SetStringField(TEXT("name"), Info.ServiceNames[i]);
            SvcArr.Add(MakeShareable(new FJsonValueObject(SvcObj)));
        }
        Obj->SetArrayField(TEXT("services"), SvcArr);
    }

    if (Info.Children.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ChildArr;
        for (const FMCPythonBTNodeInfo& Child : Info.Children)
        {
            ChildArr.Add(MakeShareable(new FJsonValueObject(BTNodeInfoToJson(Child))));
        }
        Obj->SetArrayField(TEXT("children"), ChildArr);
    }

    return Obj;
}

// ─── Behavior Tree UFUNCTION Implementations ────────────────────────────────

FString UMCPythonHelper::GetBehaviorTreeStructure(UBehaviorTree* BehaviorTree)
{
    if (!BehaviorTree || !BehaviorTree->RootNode)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree or empty tree.\"}");
    }

    FMCPythonBTNodeInfo RootInfo = SerializeBTNode(BehaviorTree->RootNode);
    TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
    ResultObj->SetBoolField(TEXT("success"), true);
    ResultObj->SetObjectField(TEXT("root"), BTNodeInfoToJson(RootInfo));

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(ResultObj.ToSharedRef(), Writer);
    return OutputString;
}

bool UMCPythonHelper::SetBehaviorTreeBlackboard(UBehaviorTree* BehaviorTree, UBlackboardData* BlackboardData)
{
    if (!BehaviorTree) return false;

    BehaviorTree->BlackboardAsset = BlackboardData;
    BehaviorTree->MarkPackageDirty();
    return true;
}

FString UMCPythonHelper::GetBehaviorTreeNodeDetails(UBehaviorTree* BehaviorTree, const FString& NodeName)
{
    if (!BehaviorTree || !BehaviorTree->RootNode)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree or empty tree.\"}");
    }

    UBTNode* FoundNode = FindNodeByName(BehaviorTree->RootNode, NodeName);
    if (!FoundNode)
    {
        TSharedPtr<FJsonObject> ErrObj = MakeShareable(new FJsonObject());
        ErrObj->SetBoolField(TEXT("success"), false);
        ErrObj->SetStringField(TEXT("message"), FString::Printf(TEXT("Node '%s' not found in behavior tree."), *NodeName));
        FString ErrStr;
        auto ErrWriter = TJsonWriterFactory<>::Create(&ErrStr);
        FJsonSerializer::Serialize(ErrObj.ToSharedRef(), ErrWriter);
        return ErrStr;
    }

    TSharedPtr<FJsonObject> JsonObj = MakeShareable(new FJsonObject());
    JsonObj->SetBoolField(TEXT("success"), true);
    JsonObj->SetStringField(TEXT("node_name"), FoundNode->GetNodeName());
    JsonObj->SetStringField(TEXT("node_class"), FoundNode->GetClass()->GetName());

    // Serialize EditAnywhere properties
    TSharedPtr<FJsonObject> PropsObj = MakeShareable(new FJsonObject());
    for (TFieldIterator<FProperty> PropIt(FoundNode->GetClass()); PropIt; ++PropIt)
    {
        FProperty* Prop = *PropIt;
        if (!Prop->HasAnyPropertyFlags(CPF_Edit)) continue;

        FString ValueStr;
        const void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(FoundNode);
        Prop->ExportText_Direct(ValueStr, ValueAddr, nullptr, FoundNode, PPF_None);
        PropsObj->SetStringField(Prop->GetName(), ValueStr);
    }
    JsonObj->SetObjectField(TEXT("properties"), PropsObj);

    // If composite node, include services and child count
    UBTCompositeNode* CompNode = Cast<UBTCompositeNode>(FoundNode);
    if (CompNode)
    {
        JsonObj->SetNumberField(TEXT("child_count"), CompNode->Children.Num());

        TArray<TSharedPtr<FJsonValue>> ServicesArr;
        for (UBTService* Svc : CompNode->Services)
        {
            if (Svc)
            {
                TSharedPtr<FJsonObject> SvcObj = MakeShareable(new FJsonObject());
                SvcObj->SetStringField(TEXT("name"), Svc->GetNodeName());
                SvcObj->SetStringField(TEXT("class"), Svc->GetClass()->GetName());
                ServicesArr.Add(MakeShareable(new FJsonValueObject(SvcObj)));
            }
        }
        if (ServicesArr.Num() > 0)
        {
            JsonObj->SetArrayField(TEXT("services"), ServicesArr);
        }
    }

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(JsonObj.ToSharedRef(), Writer);
    return OutputString;
}

FString UMCPythonHelper::GetSelectedBTNodes()
{
    if (!GEditor)
    {
        return TEXT("{\"success\":false,\"message\":\"GEditor is null.\"}");
    }

    auto* Subsystem = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
    if (!Subsystem)
    {
        return TEXT("{\"success\":false,\"message\":\"AssetEditorSubsystem not available.\"}");
    }

    for (UObject* Asset : Subsystem->GetAllEditedAssets())
    {
        UBehaviorTree* BT = Cast<UBehaviorTree>(Asset);
        if (!BT) continue;

        IAssetEditorInstance* EditorInstance = Subsystem->FindEditorForAsset(Asset, false);
        FAssetEditorToolkit* EditorToolkit = static_cast<FAssetEditorToolkit*>(EditorInstance);
        if (!EditorToolkit) continue;

        TSharedPtr<SDockTab> Tab = EditorToolkit->GetTabManager()->GetOwnerTab();
        if (!Tab.IsValid() || !Tab->IsForeground()) continue;

        FBehaviorTreeEditor* BTEditor = static_cast<FBehaviorTreeEditor*>(EditorToolkit);
        if (!BTEditor) continue;

        FGraphPanelSelectionSet SelectedNodes = BTEditor->GetSelectedNodes();

        TArray<TSharedPtr<FJsonValue>> NodesArr;
        for (UObject* NodeObj : SelectedNodes)
        {
            UBehaviorTreeGraphNode* GraphNode = Cast<UBehaviorTreeGraphNode>(NodeObj);
            if (!GraphNode) continue;

            UBTNode* BTNode = Cast<UBTNode>(GraphNode->NodeInstance);
            if (!BTNode) continue;

            TSharedPtr<FJsonObject> NodeJson = MakeShareable(new FJsonObject());
            NodeJson->SetStringField(TEXT("node_name"), BTNode->GetNodeName());
            NodeJson->SetStringField(TEXT("node_class"), BTNode->GetClass()->GetName());

            // Classify node type
            FString NodeType;
            if (Cast<UBTCompositeNode>(BTNode))
                NodeType = TEXT("composite");
            else if (Cast<UBTTaskNode>(BTNode))
                NodeType = TEXT("task");
            else if (Cast<UBTDecorator>(BTNode))
                NodeType = TEXT("decorator");
            else if (Cast<UBTService>(BTNode))
                NodeType = TEXT("service");
            else
                NodeType = TEXT("unknown");
            NodeJson->SetStringField(TEXT("node_type"), NodeType);

            // Serialize EditAnywhere properties
            TSharedPtr<FJsonObject> PropsObj = MakeShareable(new FJsonObject());
            for (TFieldIterator<FProperty> PropIt(BTNode->GetClass()); PropIt; ++PropIt)
            {
                FProperty* Prop = *PropIt;
                if (!Prop->HasAnyPropertyFlags(CPF_Edit)) continue;

                FString ValueStr;
                const void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(BTNode);
                Prop->ExportText_Direct(ValueStr, ValueAddr, nullptr, BTNode, PPF_None);
                PropsObj->SetStringField(Prop->GetName(), ValueStr);
            }
            NodeJson->SetObjectField(TEXT("properties"), PropsObj);

            NodesArr.Add(MakeShareable(new FJsonValueObject(NodeJson)));
        }

        // Build result
        TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
        ResultObj->SetBoolField(TEXT("success"), true);
        ResultObj->SetStringField(TEXT("behavior_tree_path"), BT->GetPathName());
        ResultObj->SetArrayField(TEXT("selected_nodes"), NodesArr);
        ResultObj->SetNumberField(TEXT("count"), NodesArr.Num());

        FString ResultStr;
        TSharedRef<TJsonWriter<>> ResultWriter = TJsonWriterFactory<>::Create(&ResultStr);
        FJsonSerializer::Serialize(ResultObj.ToSharedRef(), ResultWriter);
        return ResultStr;
    }

    return TEXT("{\"success\":false,\"message\":\"No Behavior Tree editor is open in the foreground.\"}");
}

// ─── Build BT Helpers ────────────────────────────────────────────────────────

static UClass* FindBTNodeClass(const FString& ClassName)
{
    for (TObjectIterator<UClass> It; It; ++It)
    {
        UClass* Cls = *It;
        if (Cls->GetName() == ClassName &&
            Cls->IsChildOf(UBTNode::StaticClass()) &&
            !Cls->HasAnyClassFlags(CLASS_Abstract))
        {
            return Cls;
        }
    }
    return nullptr;
}

static void SetBTNodeProperties(UBTNode* Node, const TSharedPtr<FJsonObject>& PropertiesObj)
{
    if (!Node || !PropertiesObj.IsValid()) return;

    for (auto& Pair : PropertiesObj->Values)
    {
        FProperty* Prop = Node->GetClass()->FindPropertyByName(FName(*Pair.Key));
        if (!Prop) continue;

        FString ValueStr;
        if (Pair.Value->TryGetString(ValueStr))
        {
            // Already a string — use as-is
        }
        else if (Pair.Value->Type == EJson::Number)
        {
            ValueStr = FString::SanitizeFloat(Pair.Value->AsNumber());
        }
        else if (Pair.Value->Type == EJson::Boolean)
        {
            ValueStr = Pair.Value->AsBool() ? TEXT("true") : TEXT("false");
        }
        else
        {
            continue;
        }

        void* ValueAddr = Prop->ContainerPtrToValuePtr<void>(Node);

        FStructProperty* StructProp = CastField<FStructProperty>(Prop);
        if (StructProp && StructProp->Struct->FindPropertyByName(TEXT("DefaultValue")))
        {
            FString WrappedValue = FString::Printf(TEXT("(DefaultValue=%s)"), *ValueStr);
            Prop->ImportText_Direct(*WrappedValue, ValueAddr, Node, PPF_None);
        }
        else
        {
            Prop->ImportText_Direct(*ValueStr, ValueAddr, Node, PPF_None);
        }
    }
}

static UEdGraphPin* FindGraphPin(UEdGraphNode* Node, EEdGraphPinDirection Direction)
{
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == Direction)
            return Pin;
    }
    return nullptr;
}

static int32 CountSubtreeLeaves(UEdGraphNode* Node)
{
    int32 Total = 0;
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == EGPD_Output)
        {
            for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
            {
                Total += CountSubtreeLeaves(LinkedPin->GetOwningNode());
            }
        }
    }
    return FMath::Max(1, Total);
}

static void LayoutBTGraphNodes(UEdGraphNode* Node, float LeftX, float Width, float Y)
{
    const float NodeWidth = 280.0f;
    const float YStep = 200.0f;

    Node->NodePosX = (int32)(LeftX + Width / 2.0f - NodeWidth / 2.0f);
    Node->NodePosY = (int32)Y;

    float SubNodeHeight = 0.0f;
    UBehaviorTreeGraphNode* BTNode = Cast<UBehaviorTreeGraphNode>(Node);
    if (BTNode)
    {
        SubNodeHeight = (BTNode->Decorators.Num() + BTNode->Services.Num()) * 60.0f;
    }

    float ChildY = Y + YStep + SubNodeHeight;
    float ChildX = LeftX;

    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin->Direction == EGPD_Output)
        {
            for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
            {
                UEdGraphNode* Child = LinkedPin->GetOwningNode();
                int32 ChildLeaves = CountSubtreeLeaves(Child);
                float ChildWidth = ChildLeaves * (NodeWidth + 40.0f);
                LayoutBTGraphNodes(Child, ChildX, ChildWidth, ChildY);
                ChildX += ChildWidth;
            }
        }
    }
}

static bool CheckClassAncestor(UClass* NodeClass, const TCHAR* AncestorName)
{
    for (UClass* C = NodeClass; C; C = C->GetSuperClass())
    {
        if (C->GetName() == AncestorName)
            return true;
    }
    return false;
}

static UBehaviorTreeGraphNode* CreateBTGraphNodeRecursive(
    UBehaviorTreeGraph* Graph,
    UBehaviorTree* BT,
    const TSharedPtr<FJsonObject>& JsonNode)
{
    if (!JsonNode.IsValid() || !JsonNode->HasField(TEXT("node_class")))
        return nullptr;

    FString NodeClassName = JsonNode->GetStringField(TEXT("node_class"));
    UClass* NodeClass = FindBTNodeClass(NodeClassName);
    if (!NodeClass)
    {
        UE_LOG(LogTemp, Warning, TEXT("BuildBT: Class '%s' not found"), *NodeClassName);
        return nullptr;
    }

    // Create runtime node
    UBTNode* RuntimeNode = NewObject<UBTNode>(BT, NodeClass);

    // Classify node type
    bool bIsComposite = NodeClass->IsChildOf(UBTCompositeNode::StaticClass());
    bool bIsTask = NodeClass->IsChildOf(UBTTaskNode::StaticClass());
    bool bIsSimpleParallel = CheckClassAncestor(NodeClass, TEXT("BTComposite_SimpleParallel"));
    bool bIsSubtreeTask = CheckClassAncestor(NodeClass, TEXT("BTTask_RunBehavior"))
                       || CheckClassAncestor(NodeClass, TEXT("BTTask_RunBehaviorDynamic"));

    // Create appropriate graph node
    UBehaviorTreeGraphNode* GraphNode = nullptr;

    if (bIsSimpleParallel)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_SimpleParallel> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsComposite)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_Composite> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsSubtreeTask)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_SubtreeTask> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else if (bIsTask)
    {
        FGraphNodeCreator<UBehaviorTreeGraphNode_Task> Creator(*Graph);
        GraphNode = Creator.CreateNode(false);
        Creator.Finalize();
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("BuildBT: Unsupported node type for '%s'"), *NodeClassName);
        return nullptr;
    }

    // Set NodeInstance
    GraphNode->NodeInstance = RuntimeNode;

    // Set properties on the runtime node
    if (JsonNode->HasField(TEXT("properties")))
    {
        const TSharedPtr<FJsonObject>& PropsObj = JsonNode->GetObjectField(TEXT("properties"));
        SetBTNodeProperties(RuntimeNode, PropsObj);
    }

    // Add decorators as sub-nodes
    if (JsonNode->HasField(TEXT("decorators")))
    {
        const TArray<TSharedPtr<FJsonValue>>& DecoratorsArr = JsonNode->GetArrayField(TEXT("decorators"));
        for (const auto& DecVal : DecoratorsArr)
        {
            const TSharedPtr<FJsonObject>& DecObj = DecVal->AsObject();
            if (!DecObj.IsValid() || !DecObj->HasField(TEXT("class"))) continue;

            FString DecClassName = DecObj->GetStringField(TEXT("class"));
            UClass* DecClass = FindBTNodeClass(DecClassName);
            if (!DecClass || !DecClass->IsChildOf(UBTDecorator::StaticClass()))
            {
                UE_LOG(LogTemp, Warning, TEXT("BuildBT: Decorator class '%s' not found or invalid"), *DecClassName);
                continue;
            }

            UBTDecorator* DecRuntime = NewObject<UBTDecorator>(BT, DecClass);
            if (DecObj->HasField(TEXT("properties")))
            {
                SetBTNodeProperties(DecRuntime, DecObj->GetObjectField(TEXT("properties")));
            }

            UBehaviorTreeGraphNode_Decorator* DecGraphNode =
                NewObject<UBehaviorTreeGraphNode_Decorator>(Graph);
            DecGraphNode->NodeInstance = DecRuntime;
            GraphNode->AddSubNode(DecGraphNode, Graph);
        }
    }

    // Add services as sub-nodes
    if (JsonNode->HasField(TEXT("services")))
    {
        const TArray<TSharedPtr<FJsonValue>>& ServicesArr = JsonNode->GetArrayField(TEXT("services"));
        for (const auto& SvcVal : ServicesArr)
        {
            const TSharedPtr<FJsonObject>& SvcObj = SvcVal->AsObject();
            if (!SvcObj.IsValid() || !SvcObj->HasField(TEXT("class"))) continue;

            FString SvcClassName = SvcObj->GetStringField(TEXT("class"));
            UClass* SvcClass = FindBTNodeClass(SvcClassName);
            if (!SvcClass || !SvcClass->IsChildOf(UBTService::StaticClass()))
            {
                UE_LOG(LogTemp, Warning, TEXT("BuildBT: Service class '%s' not found or invalid"), *SvcClassName);
                continue;
            }

            UBTService* SvcRuntime = NewObject<UBTService>(BT, SvcClass);
            if (SvcObj->HasField(TEXT("properties")))
            {
                SetBTNodeProperties(SvcRuntime, SvcObj->GetObjectField(TEXT("properties")));
            }

            UBehaviorTreeGraphNode_Service* SvcGraphNode =
                NewObject<UBehaviorTreeGraphNode_Service>(Graph);
            SvcGraphNode->NodeInstance = SvcRuntime;
            GraphNode->AddSubNode(SvcGraphNode, Graph);
        }
    }

    // Recurse for children (only composites have children)
    if (bIsComposite && JsonNode->HasField(TEXT("children")))
    {
        const TArray<TSharedPtr<FJsonValue>>& ChildrenArr = JsonNode->GetArrayField(TEXT("children"));
        UEdGraphPin* OutputPin = FindGraphPin(GraphNode, EGPD_Output);

        if (OutputPin)
        {
            for (const auto& ChildVal : ChildrenArr)
            {
                const TSharedPtr<FJsonObject>& ChildObj = ChildVal->AsObject();
                if (!ChildObj.IsValid()) continue;

                UBehaviorTreeGraphNode* ChildGraphNode =
                    CreateBTGraphNodeRecursive(Graph, BT, ChildObj);

                if (ChildGraphNode)
                {
                    UEdGraphPin* ChildInputPin = FindGraphPin(ChildGraphNode, EGPD_Input);
                    if (ChildInputPin)
                    {
                        OutputPin->MakeLinkTo(ChildInputPin);
                    }
                }
            }
        }
    }

    return GraphNode;
}

// ─── BuildBehaviorTree UFUNCTION ─────────────────────────────────────────────

FString UMCPythonHelper::BuildBehaviorTree(UBehaviorTree* BehaviorTree, const FString& TreeStructureJson)
{
    if (!BehaviorTree)
    {
        return TEXT("{\"success\":false,\"message\":\"Invalid BehaviorTree asset.\"}");
    }

    // Parse JSON
    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(TreeStructureJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
    {
        return TEXT("{\"success\":false,\"message\":\"Failed to parse JSON input.\"}");
    }

    // Get BT graph — create if missing (e.g. asset created without factory)
    UBehaviorTreeGraph* BTGraph = Cast<UBehaviorTreeGraph>(BehaviorTree->BTGraph);
    if (!BTGraph)
    {
        UBehaviorTreeGraph* NewGraph = NewObject<UBehaviorTreeGraph>(BehaviorTree, NAME_None, RF_Transactional);
        NewGraph->Schema = UEdGraphSchema_BehaviorTree::StaticClass();
        BehaviorTree->BTGraph = NewGraph;

        const UEdGraphSchema* Schema = NewGraph->GetSchema();
        if (Schema)
        {
            Schema->CreateDefaultNodesForGraph(*NewGraph);
        }

        BTGraph = NewGraph;
    }

    // Find root graph node
    UBehaviorTreeGraphNode_Root* RootGraphNode = nullptr;
    for (UEdGraphNode* Node : BTGraph->Nodes)
    {
        RootGraphNode = Cast<UBehaviorTreeGraphNode_Root>(Node);
        if (RootGraphNode) break;
    }

    if (!RootGraphNode)
    {
        return TEXT("{\"success\":false,\"message\":\"No root node found in BT graph.\"}");
    }

    // Remove all existing non-root graph nodes
    TArray<UEdGraphNode*> NodesToRemove;
    for (UEdGraphNode* Node : BTGraph->Nodes)
    {
        if (Node != RootGraphNode)
        {
            NodesToRemove.Add(Node);
        }
    }
    for (UEdGraphNode* Node : NodesToRemove)
    {
        BTGraph->RemoveNode(Node);
    }

    // Clear root pin links and sub-nodes
    for (UEdGraphPin* Pin : RootGraphNode->Pins)
    {
        Pin->BreakAllPinLinks();
    }
    RootGraphNode->Decorators.Empty();
    RootGraphNode->Services.Empty();

    // Create graph nodes from JSON
    UBehaviorTreeGraphNode* FirstChild = CreateBTGraphNodeRecursive(BTGraph, BehaviorTree, JsonObj);

    if (!FirstChild)
    {
        return TEXT("{\"success\":false,\"message\":\"Failed to create root node from JSON. Check node_class names.\"}");
    }

    // Connect root to first child
    UEdGraphPin* RootOutput = FindGraphPin(RootGraphNode, EGPD_Output);
    UEdGraphPin* ChildInput = FindGraphPin(FirstChild, EGPD_Input);
    if (RootOutput && ChildInput)
    {
        RootOutput->MakeLinkTo(ChildInput);
    }

    // Layout nodes BEFORE UpdateAsset — RebuildChildOrder sorts children by NodePosX
    float TotalWidth = CountSubtreeLeaves(RootGraphNode) * 320.0f;
    LayoutBTGraphNodes(RootGraphNode, 0.0f, TotalWidth, 0.0f);

    // Compile graph → runtime tree (uses node positions for child ordering)
    BTGraph->UpdateAsset();

    BehaviorTree->MarkPackageDirty();

    // Return success
    TSharedPtr<FJsonObject> ResultObj = MakeShareable(new FJsonObject());
    ResultObj->SetBoolField(TEXT("success"), true);
    ResultObj->SetStringField(TEXT("message"), TEXT("Behavior tree built successfully from JSON."));

    FString ResultStr;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&ResultStr);
    FJsonSerializer::Serialize(ResultObj.ToSharedRef(), Writer);
    return ResultStr;
}

// ─── ListBTNodeClasses UFUNCTION ─────────────────────────────────────────────

FString UMCPythonHelper::ListBTNodeClasses()
{
    TArray<TSharedPtr<FJsonValue>> Composites, Tasks, Decorators, Services;

    for (TObjectIterator<UClass> It; It; ++It)
    {
        UClass* Cls = *It;
        if (Cls->HasAnyClassFlags(CLASS_Abstract | CLASS_Deprecated | CLASS_NewerVersionExists))
            continue;

        FString ClassName = Cls->GetName();
        TSharedPtr<FJsonValue> NameVal = MakeShareable(new FJsonValueString(ClassName));

        if (Cls->IsChildOf(UBTCompositeNode::StaticClass()))
            Composites.Add(NameVal);
        else if (Cls->IsChildOf(UBTTaskNode::StaticClass()))
            Tasks.Add(NameVal);
        else if (Cls->IsChildOf(UBTDecorator::StaticClass()))
            Decorators.Add(NameVal);
        else if (Cls->IsChildOf(UBTService::StaticClass()))
            Services.Add(NameVal);
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetArrayField(TEXT("composites"), Composites);
    Result->SetArrayField(TEXT("tasks"), Tasks);
    Result->SetArrayField(TEXT("decorators"), Decorators);
    Result->SetArrayField(TEXT("services"), Services);

    FString OutputString;
    TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&OutputString);
    FJsonSerializer::Serialize(Result.ToSharedRef(), Writer);
    return OutputString;
}

// ─── Blueprint Graph Helpers (internal) ──────────────────────────────────────

static FString MakeJsonError(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetBoolField(TEXT("success"), false);
    Obj->SetStringField(TEXT("message"), Message);
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

static FString MakeJsonSuccess(const FString& Message)
{
    TSharedPtr<FJsonObject> Obj = MakeShareable(new FJsonObject());
    Obj->SetBoolField(TEXT("success"), true);
    Obj->SetStringField(TEXT("message"), Message);
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

static FString SerializeJsonObj(TSharedPtr<FJsonObject> Obj)
{
    FString Out;
    TSharedRef<TJsonWriter<>> W = TJsonWriterFactory<>::Create(&Out);
    FJsonSerializer::Serialize(Obj.ToSharedRef(), W);
    return Out;
}

static UEdGraph* FindGraphByName(UBlueprint* Blueprint, const FString& GraphName)
{
    for (UEdGraph* Graph : Blueprint->UbergraphPages)
    {
        if (Graph && Graph->GetName() == GraphName)
            return Graph;
    }
    for (UEdGraph* Graph : Blueprint->FunctionGraphs)
    {
        if (Graph && Graph->GetName() == GraphName)
            return Graph;
    }
    return nullptr;
}

static UEdGraphNode* FindBPNodeByName(UEdGraph* Graph, const FString& NodeName)
{
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node && Node->GetName() == NodeName)
            return Node;
    }
    return nullptr;
}

static UEdGraphPin* FindPinByName(UEdGraphNode* Node, const FString& PinName, EEdGraphPinDirection Direction = EGPD_MAX)
{
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (!Pin || Pin->bHidden) continue;
        if (Direction != EGPD_MAX && Pin->Direction != Direction) continue;

        // Match by internal name
        if (Pin->GetName() == PinName)
            return Pin;
        // Match by friendly name
        FString Friendly = Pin->PinFriendlyName.ToString();
        if (!Friendly.IsEmpty() && Friendly == PinName)
            return Pin;
    }
    return nullptr;
}

// ─── GetBlueprintGraphInfo ───────────────────────────────────────────────────

FString UMCPythonHelper::GetBlueprintGraphInfo(UBlueprint* Blueprint, const FString& GraphName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found in Blueprint."), *GraphName));

    TArray<TSharedPtr<FJsonValue>> NodesArr;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node) continue;

        TSharedPtr<FJsonObject> NodeObj = MakeShareable(new FJsonObject());
        NodeObj->SetStringField(TEXT("node_name"), Node->GetName());
        NodeObj->SetStringField(TEXT("node_title"), Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
        NodeObj->SetStringField(TEXT("node_class"), Node->GetClass()->GetName());
        if (!Node->NodeComment.IsEmpty())
            NodeObj->SetStringField(TEXT("comment"), Node->NodeComment);
        NodeObj->SetNumberField(TEXT("pos_x"), Node->NodePosX);
        NodeObj->SetNumberField(TEXT("pos_y"), Node->NodePosY);

        TArray<TSharedPtr<FJsonValue>> PinsArr;
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (!Pin || Pin->bHidden) continue;
            TSharedPtr<FJsonObject> PinObj = MakeShareable(new FJsonObject());
            PinObj->SetStringField(TEXT("pin_name"), Pin->GetName());
            FString Friendly = Pin->PinFriendlyName.ToString();
            if (!Friendly.IsEmpty())
                PinObj->SetStringField(TEXT("friendly_name"), Friendly);
            PinObj->SetStringField(TEXT("direction"), (Pin->Direction == EGPD_Input) ? TEXT("Input") : TEXT("Output"));
            PinObj->SetStringField(TEXT("type"), Pin->PinType.PinCategory.ToString());
            if (Pin->PinType.PinSubCategoryObject.IsValid())
                PinObj->SetStringField(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName());
            if (!Pin->DefaultValue.IsEmpty())
                PinObj->SetStringField(TEXT("default_value"), Pin->DefaultValue);

            // Linked pins
            if (Pin->LinkedTo.Num() > 0)
            {
                TArray<TSharedPtr<FJsonValue>> LinksArr;
                for (UEdGraphPin* Linked : Pin->LinkedTo)
                {
                    if (!Linked || !Linked->GetOwningNode()) continue;
                    TSharedPtr<FJsonObject> LinkObj = MakeShareable(new FJsonObject());
                    LinkObj->SetStringField(TEXT("node_name"), Linked->GetOwningNode()->GetName());
                    LinkObj->SetStringField(TEXT("pin_name"), Linked->GetName());
                    LinksArr.Add(MakeShareable(new FJsonValueObject(LinkObj)));
                }
                PinObj->SetArrayField(TEXT("linked_to"), LinksArr);
            }
            PinsArr.Add(MakeShareable(new FJsonValueObject(PinObj)));
        }
        NodeObj->SetArrayField(TEXT("pins"), PinsArr);
        NodesArr.Add(MakeShareable(new FJsonValueObject(NodeObj)));
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("graph_name"), GraphName);
    Result->SetNumberField(TEXT("node_count"), Graph->Nodes.Num());
    Result->SetArrayField(TEXT("nodes"), NodesArr);
    return SerializeJsonObj(Result);
}

// ─── ListCallableFunctions ───────────────────────────────────────────────────

FString UMCPythonHelper::ListCallableFunctions(UBlueprint* Blueprint, const FString& Filter)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UClass* GenClass = Blueprint->GeneratedClass;
    if (!GenClass)
        return MakeJsonError(TEXT("Blueprint has no generated class. Compile it first."));

    TArray<TSharedPtr<FJsonValue>> FuncsArr;
    FString FilterLower = Filter.ToLower();

    // Collect from the generated class and all parent classes
    for (UClass* Cls = GenClass; Cls; Cls = Cls->GetSuperClass())
    {
        for (TFieldIterator<UFunction> FuncIt(Cls, EFieldIteratorFlags::ExcludeSuper); FuncIt; ++FuncIt)
        {
            UFunction* Func = *FuncIt;
            if (!Func || !Func->HasAnyFunctionFlags(FUNC_BlueprintCallable))
                continue;

            FString FuncName = Func->GetName();
            FString ClassName = Cls->GetName();

            if (!FilterLower.IsEmpty())
            {
                if (!FuncName.ToLower().Contains(FilterLower) && !ClassName.ToLower().Contains(FilterLower))
                    continue;
            }

            TSharedPtr<FJsonObject> FuncObj = MakeShareable(new FJsonObject());
            FuncObj->SetStringField(TEXT("function_name"), FuncName);
            FuncObj->SetStringField(TEXT("class_name"), ClassName);
            FuncObj->SetBoolField(TEXT("is_pure"), Func->HasAnyFunctionFlags(FUNC_BlueprintPure));
            FuncObj->SetBoolField(TEXT("is_static"), Func->HasAnyFunctionFlags(FUNC_Static));

            // Parameters
            TArray<TSharedPtr<FJsonValue>> ParamsArr;
            for (TFieldIterator<FProperty> PropIt(Func); PropIt; ++PropIt)
            {
                FProperty* Prop = *PropIt;
                TSharedPtr<FJsonObject> ParamObj = MakeShareable(new FJsonObject());
                ParamObj->SetStringField(TEXT("name"), Prop->GetName());
                ParamObj->SetStringField(TEXT("type"), Prop->GetCPPType());
                ParamObj->SetBoolField(TEXT("is_return"), Prop->HasAnyPropertyFlags(CPF_ReturnParm));
                ParamObj->SetBoolField(TEXT("is_output"), Prop->HasAnyPropertyFlags(CPF_OutParm));
                ParamsArr.Add(MakeShareable(new FJsonValueObject(ParamObj)));
            }
            FuncObj->SetArrayField(TEXT("parameters"), ParamsArr);
            FuncsArr.Add(MakeShareable(new FJsonValueObject(FuncObj)));
        }
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetNumberField(TEXT("count"), FuncsArr.Num());
    Result->SetArrayField(TEXT("functions"), FuncsArr);
    return SerializeJsonObj(Result);
}

// ─── ListBlueprintVariables ──────────────────────────────────────────────────

FString UMCPythonHelper::ListBlueprintVariables(UBlueprint* Blueprint)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    TArray<TSharedPtr<FJsonValue>> VarsArr;
    for (const FBPVariableDescription& Var : Blueprint->NewVariables)
    {
        TSharedPtr<FJsonObject> VarObj = MakeShareable(new FJsonObject());
        VarObj->SetStringField(TEXT("name"), Var.VarName.ToString());
        VarObj->SetStringField(TEXT("type"), Var.VarType.PinCategory.ToString());
        if (Var.VarType.PinSubCategoryObject.IsValid())
            VarObj->SetStringField(TEXT("sub_type"), Var.VarType.PinSubCategoryObject->GetName());
        VarObj->SetBoolField(TEXT("is_array"), Var.VarType.IsArray());
        VarObj->SetBoolField(TEXT("is_set"), Var.VarType.IsSet());
        VarObj->SetBoolField(TEXT("is_map"), Var.VarType.IsMap());
        if (!Var.DefaultValue.IsEmpty())
            VarObj->SetStringField(TEXT("default_value"), Var.DefaultValue);
        VarsArr.Add(MakeShareable(new FJsonValueObject(VarObj)));
    }

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetNumberField(TEXT("count"), VarsArr.Num());
    Result->SetArrayField(TEXT("variables"), VarsArr);
    return SerializeJsonObj(Result);
}

// ─── Blueprint Node Creation Helpers ─────────────────────────────────────────

static UEdGraphNode* CreateBPNodeFromJson(UEdGraph* Graph, UBlueprint* Blueprint, const TSharedPtr<FJsonObject>& NodeJson, FString& OutError)
{
    FString NodeType;
    if (!NodeJson->TryGetStringField(TEXT("type"), NodeType))
    {
        OutError = TEXT("Node JSON missing 'type' field.");
        return nullptr;
    }

    double PosXd = 0, PosYd = 0;
    NodeJson->TryGetNumberField(TEXT("pos_x"), PosXd);
    NodeJson->TryGetNumberField(TEXT("pos_y"), PosYd);
    int32 PosX = (int32)PosXd;
    int32 PosY = (int32)PosYd;

    UEdGraphNode* NewNode = nullptr;

    if (NodeType == TEXT("CallFunction"))
    {
        FString TargetClass, FunctionName;
        if (!NodeJson->TryGetStringField(TEXT("function_name"), FunctionName))
        {
            OutError = TEXT("CallFunction node missing 'function_name'.");
            return nullptr;
        }
        NodeJson->TryGetStringField(TEXT("target"), TargetClass);

        // Find the UFunction
        UFunction* TargetFunc = nullptr;
        if (!TargetClass.IsEmpty())
        {
            UClass* Cls = FindObject<UClass>(nullptr, *FString::Printf(TEXT("/Script/Engine.%s"), *TargetClass));
            if (!Cls)
                Cls = FindFirstObject<UClass>(*TargetClass, EFindFirstObjectOptions::NativeFirst);
            if (Cls)
                TargetFunc = Cls->FindFunctionByName(FName(*FunctionName));
        }

        if (!TargetFunc)
        {
            // Search in the Blueprint's generated class hierarchy
            for (UClass* Cls = Blueprint->GeneratedClass; Cls && !TargetFunc; Cls = Cls->GetSuperClass())
            {
                TargetFunc = Cls->FindFunctionByName(FName(*FunctionName));
            }
        }

        if (!TargetFunc)
        {
            OutError = FString::Printf(TEXT("Function '%s' not found (target: '%s')."), *FunctionName, *TargetClass);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_CallFunction> Creator(*Graph);
        UK2Node_CallFunction* FuncNode = Creator.CreateNode(false);
        FuncNode->SetFromFunction(TargetFunc);
        FuncNode->NodePosX = PosX;
        FuncNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = FuncNode;
    }
    else if (NodeType == TEXT("Event"))
    {
        FString EventName;
        if (!NodeJson->TryGetStringField(TEXT("event_name"), EventName))
        {
            OutError = TEXT("Event node missing 'event_name'.");
            return nullptr;
        }

        UClass* EventClass = Blueprint->GeneratedClass ? Blueprint->GeneratedClass : Blueprint->ParentClass;
        UFunction* EventFunc = EventClass ? EventClass->FindFunctionByName(FName(*EventName)) : nullptr;

        if (!EventFunc)
        {
            OutError = FString::Printf(TEXT("Event function '%s' not found in class hierarchy."), *EventName);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_Event> Creator(*Graph);
        UK2Node_Event* EventNode = Creator.CreateNode(false);
        EventNode->EventReference.SetExternalMember(FName(*EventName), EventClass);
        EventNode->bOverrideFunction = true;
        EventNode->NodePosX = PosX;
        EventNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = EventNode;
    }
    else if (NodeType == TEXT("CustomEvent"))
    {
        FString EventName;
        if (!NodeJson->TryGetStringField(TEXT("event_name"), EventName))
        {
            OutError = TEXT("CustomEvent node missing 'event_name'.");
            return nullptr;
        }

        UK2Node_CustomEvent* CustomNode = UK2Node_CustomEvent::CreateFromFunction(
            FVector2D(PosX, PosY), Graph, EventName, nullptr, false);
        if (!CustomNode)
        {
            OutError = FString::Printf(TEXT("Failed to create CustomEvent '%s'."), *EventName);
            return nullptr;
        }
        NewNode = CustomNode;
    }
    else if (NodeType == TEXT("Branch"))
    {
        FGraphNodeCreator<UK2Node_IfThenElse> Creator(*Graph);
        UK2Node_IfThenElse* BranchNode = Creator.CreateNode(false);
        BranchNode->NodePosX = PosX;
        BranchNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = BranchNode;
    }
    else if (NodeType == TEXT("Sequence"))
    {
        FGraphNodeCreator<UK2Node_ExecutionSequence> Creator(*Graph);
        UK2Node_ExecutionSequence* SeqNode = Creator.CreateNode(false);
        SeqNode->NodePosX = PosX;
        SeqNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = SeqNode;
    }
    else if (NodeType == TEXT("VariableGet"))
    {
        FString VarName;
        if (!NodeJson->TryGetStringField(TEXT("variable_name"), VarName))
        {
            OutError = TEXT("VariableGet node missing 'variable_name'.");
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_VariableGet> Creator(*Graph);
        UK2Node_VariableGet* GetNode = Creator.CreateNode(false);
        GetNode->VariableReference.SetSelfMember(FName(*VarName));
        GetNode->NodePosX = PosX;
        GetNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = GetNode;
    }
    else if (NodeType == TEXT("VariableSet"))
    {
        FString VarName;
        if (!NodeJson->TryGetStringField(TEXT("variable_name"), VarName))
        {
            OutError = TEXT("VariableSet node missing 'variable_name'.");
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_VariableSet> Creator(*Graph);
        UK2Node_VariableSet* SetNode = Creator.CreateNode(false);
        SetNode->VariableReference.SetSelfMember(FName(*VarName));
        SetNode->NodePosX = PosX;
        SetNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = SetNode;
    }
    else if (NodeType == TEXT("MacroInstance"))
    {
        FString MacroName;
        if (!NodeJson->TryGetStringField(TEXT("macro_name"), MacroName))
        {
            OutError = TEXT("MacroInstance node missing 'macro_name'.");
            return nullptr;
        }

        // Search for macro graph in the Blueprint and its parents
        UEdGraph* MacroGraph = nullptr;
        for (UBlueprint* SearchBP = Blueprint; SearchBP && !MacroGraph; SearchBP = Cast<UBlueprint>(SearchBP->ParentClass->ClassGeneratedBy))
        {
            for (UEdGraph* MGraph : SearchBP->MacroGraphs)
            {
                if (MGraph && MGraph->GetName() == MacroName)
                {
                    MacroGraph = MGraph;
                    break;
                }
            }
            if (!SearchBP->ParentClass || !SearchBP->ParentClass->ClassGeneratedBy)
                break;
        }

        // Also search engine-level macros (e.g., ForEachLoop)
        if (!MacroGraph)
        {
            UBlueprint* MacroLibBP = LoadObject<UBlueprint>(nullptr, TEXT("/Engine/EditorBlueprintResources/StandardMacros.StandardMacros"));
            if (MacroLibBP)
            {
                for (UEdGraph* MGraph : MacroLibBP->MacroGraphs)
                {
                    if (MGraph && MGraph->GetName() == MacroName)
                    {
                        MacroGraph = MGraph;
                        break;
                    }
                }
            }
        }

        if (!MacroGraph)
        {
            OutError = FString::Printf(TEXT("Macro '%s' not found."), *MacroName);
            return nullptr;
        }

        FGraphNodeCreator<UK2Node_MacroInstance> Creator(*Graph);
        UK2Node_MacroInstance* MacroNode = Creator.CreateNode(false);
        MacroNode->SetMacroGraph(MacroGraph);
        MacroNode->NodePosX = PosX;
        MacroNode->NodePosY = PosY;
        Creator.Finalize();
        NewNode = MacroNode;
    }
    else
    {
        OutError = FString::Printf(TEXT("Unknown node type '%s'. Supported: CallFunction, Event, CustomEvent, Branch, Sequence, VariableGet, VariableSet, MacroInstance."), *NodeType);
        return nullptr;
    }

    // Set pin defaults if specified
    if (NewNode && NodeJson->HasField(TEXT("pin_defaults")))
    {
        const TSharedPtr<FJsonObject>& PinDefaults = NodeJson->GetObjectField(TEXT("pin_defaults"));
        for (auto& Pair : PinDefaults->Values)
        {
            UEdGraphPin* Pin = FindPinByName(NewNode, Pair.Key, EGPD_Input);
            if (Pin)
            {
                FString Value;
                if (Pair.Value->TryGetString(Value))
                {
                    Pin->DefaultValue = Value;
                }
            }
        }
    }

    return NewNode;
}

// ─── AddBlueprintNode UFUNCTION ──────────────────────────────────────────────

FString UMCPythonHelper::AddBlueprintNode(UBlueprint* Blueprint, const FString& GraphName, const FString& NodeJson)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(NodeJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
        return MakeJsonError(TEXT("Failed to parse NodeJson."));

    FString Error;
    UEdGraphNode* NewNode = CreateBPNodeFromJson(Graph, Blueprint, JsonObj, Error);
    if (!NewNode)
        return MakeJsonError(Error);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("node_name"), NewNode->GetName());
    Result->SetStringField(TEXT("node_title"), NewNode->GetNodeTitle(ENodeTitleType::FullTitle).ToString());
    Result->SetStringField(TEXT("message"), FString::Printf(TEXT("Node '%s' added to graph '%s'."), *NewNode->GetNodeTitle(ENodeTitleType::FullTitle).ToString(), *GraphName));

    // Return pin info so caller knows how to connect
    TArray<TSharedPtr<FJsonValue>> PinsArr;
    for (UEdGraphPin* Pin : NewNode->Pins)
    {
        if (!Pin || Pin->bHidden) continue;
        TSharedPtr<FJsonObject> PinObj = MakeShareable(new FJsonObject());
        PinObj->SetStringField(TEXT("pin_name"), Pin->GetName());
        FString Friendly = Pin->PinFriendlyName.ToString();
        if (!Friendly.IsEmpty())
            PinObj->SetStringField(TEXT("friendly_name"), Friendly);
        PinObj->SetStringField(TEXT("direction"), (Pin->Direction == EGPD_Input) ? TEXT("Input") : TEXT("Output"));
        PinObj->SetStringField(TEXT("type"), Pin->PinType.PinCategory.ToString());
        PinsArr.Add(MakeShareable(new FJsonValueObject(PinObj)));
    }
    Result->SetArrayField(TEXT("pins"), PinsArr);
    return SerializeJsonObj(Result);
}

// ─── ConnectBlueprintPins UFUNCTION ──────────────────────────────────────────

FString UMCPythonHelper::ConnectBlueprintPins(UBlueprint* Blueprint, const FString& GraphName,
    const FString& SourceNodeName, const FString& SourcePinName,
    const FString& TargetNodeName, const FString& TargetPinName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* SourceNode = FindBPNodeByName(Graph, SourceNodeName);
    if (!SourceNode)
        return MakeJsonError(FString::Printf(TEXT("Source node '%s' not found."), *SourceNodeName));

    UEdGraphNode* TargetNode = FindBPNodeByName(Graph, TargetNodeName);
    if (!TargetNode)
        return MakeJsonError(FString::Printf(TEXT("Target node '%s' not found."), *TargetNodeName));

    UEdGraphPin* SourcePin = FindPinByName(SourceNode, SourcePinName);
    if (!SourcePin)
    {
        TArray<FString> PinNames;
        for (UEdGraphPin* P : SourceNode->Pins) { if (P && !P->bHidden) PinNames.Add(P->GetName()); }
        return MakeJsonError(FString::Printf(TEXT("Pin '%s' not found on node '%s'. Available: %s"),
            *SourcePinName, *SourceNodeName, *FString::Join(PinNames, TEXT(", "))));
    }

    UEdGraphPin* TargetPin = FindPinByName(TargetNode, TargetPinName);
    if (!TargetPin)
    {
        TArray<FString> PinNames;
        for (UEdGraphPin* P : TargetNode->Pins) { if (P && !P->bHidden) PinNames.Add(P->GetName()); }
        return MakeJsonError(FString::Printf(TEXT("Pin '%s' not found on node '%s'. Available: %s"),
            *TargetPinName, *TargetNodeName, *FString::Join(PinNames, TEXT(", "))));
    }

    // Verify directions are compatible (output -> input)
    if (SourcePin->Direction == TargetPin->Direction)
        return MakeJsonError(FString::Printf(TEXT("Cannot connect pins with same direction (%s)."),
            SourcePin->Direction == EGPD_Input ? TEXT("both Input") : TEXT("both Output")));

    // Check if connection is allowed by the schema
    const UEdGraphSchema* Schema = Graph->GetSchema();
    if (Schema)
    {
        FPinConnectionResponse Response = Schema->CanCreateConnection(SourcePin, TargetPin);
        if (Response.Response == CONNECT_RESPONSE_DISALLOW)
            return MakeJsonError(FString::Printf(TEXT("Connection not allowed: %s"), *Response.Message.ToString()));
    }

    SourcePin->MakeLinkTo(TargetPin);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
    return MakeJsonSuccess(FString::Printf(TEXT("Connected %s.%s -> %s.%s"),
        *SourceNodeName, *SourcePinName, *TargetNodeName, *TargetPinName));
}

// ─── RemoveBlueprintNode UFUNCTION ───────────────────────────────────────────

FString UMCPythonHelper::RemoveBlueprintNode(UBlueprint* Blueprint, const FString& GraphName,
    const FString& NodeName)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    UEdGraphNode* Node = FindBPNodeByName(Graph, NodeName);
    if (!Node)
        return MakeJsonError(FString::Printf(TEXT("Node '%s' not found in graph '%s'."), *NodeName, *GraphName));

    // Break all pin connections first
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin)
            Pin->BreakAllPinLinks();
    }

    Graph->RemoveNode(Node);
    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    return MakeJsonSuccess(FString::Printf(TEXT("Node '%s' removed from graph '%s'."), *NodeName, *GraphName));
}

// ─── BuildBlueprintGraph UFUNCTION ───────────────────────────────────────────

static void LayoutBPGraphNodes(const TMap<FString, UEdGraphNode*>& NodeMap,
    const TArray<TSharedPtr<FJsonValue>>& Connections)
{
    // Simple left-to-right layout based on execution flow
    // Assign columns based on connection depth
    TMap<FString, int32> NodeColumns;
    TSet<FString> Visited;

    // Find nodes with no incoming exec connections (roots)
    TSet<FString> HasIncoming;
    for (auto& ConnVal : Connections)
    {
        const TSharedPtr<FJsonObject>& Conn = ConnVal->AsObject();
        if (!Conn.IsValid()) continue;
        FString TargetNodeId;
        if (Conn->TryGetStringField(TEXT("target_node"), TargetNodeId))
            HasIncoming.Add(TargetNodeId);
    }

    // Assign column 0 to roots, then propagate
    int32 Col = 0;
    for (auto& Pair : NodeMap)
    {
        if (!HasIncoming.Contains(Pair.Key))
            NodeColumns.Add(Pair.Key, 0);
    }

    // Propagate columns through connections
    for (auto& ConnVal : Connections)
    {
        const TSharedPtr<FJsonObject>& Conn = ConnVal->AsObject();
        if (!Conn.IsValid()) continue;
        FString SourceId, TargetId;
        Conn->TryGetStringField(TEXT("source_node"), SourceId);
        Conn->TryGetStringField(TEXT("target_node"), TargetId);

        int32* SourceCol = NodeColumns.Find(SourceId);
        int32 SC = SourceCol ? *SourceCol : 0;
        int32* TargetCol = NodeColumns.Find(TargetId);
        if (!TargetCol || *TargetCol <= SC)
            NodeColumns.Add(TargetId, SC + 1);
    }

    // Count nodes per column for Y positioning
    TMap<int32, int32> ColumnRowCount;
    const float XStep = 400.0f;
    const float YStep = 200.0f;

    for (auto& Pair : NodeMap)
    {
        int32* ColPtr = NodeColumns.Find(Pair.Key);
        int32 C = ColPtr ? *ColPtr : 0;
        int32* RowPtr = ColumnRowCount.Find(C);
        int32 Row = RowPtr ? *RowPtr : 0;

        Pair.Value->NodePosX = (int32)(C * XStep);
        Pair.Value->NodePosY = (int32)(Row * YStep);

        ColumnRowCount.Add(C, Row + 1);
    }
}

FString UMCPythonHelper::BuildBlueprintGraph(UBlueprint* Blueprint, const FString& GraphName,
    const FString& GraphJson)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    UEdGraph* Graph = FindGraphByName(Blueprint, GraphName);
    if (!Graph)
        return MakeJsonError(FString::Printf(TEXT("Graph '%s' not found."), *GraphName));

    // Parse JSON
    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(GraphJson);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
        return MakeJsonError(TEXT("Failed to parse GraphJson."));

    if (!JsonObj->HasField(TEXT("nodes")))
        return MakeJsonError(TEXT("GraphJson missing 'nodes' array."));

    const TArray<TSharedPtr<FJsonValue>>& NodesArr = JsonObj->GetArrayField(TEXT("nodes"));
    TArray<TSharedPtr<FJsonValue>> ConnectionsArr;
    if (JsonObj->HasField(TEXT("connections")))
        ConnectionsArr = JsonObj->GetArrayField(TEXT("connections"));

    // Remove existing user-created nodes (keep root/entry nodes)
    TArray<UEdGraphNode*> NodesToRemove;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (!Node) continue;
        // Keep entry points (function entry, etc.) but remove user nodes
        // For EventGraph, we typically remove all non-essential nodes
        if (!Node->IsA<UK2Node_Event>())
        {
            NodesToRemove.Add(Node);
        }
    }
    for (UEdGraphNode* Node : NodesToRemove)
    {
        for (UEdGraphPin* Pin : Node->Pins)
        {
            if (Pin) Pin->BreakAllPinLinks();
        }
        Graph->RemoveNode(Node);
    }

    // Create nodes from JSON
    TMap<FString, UEdGraphNode*> NodeMap; // id -> node
    TArray<FString> CreationErrors;

    for (auto& NodeVal : NodesArr)
    {
        const TSharedPtr<FJsonObject>& NodeObj = NodeVal->AsObject();
        if (!NodeObj.IsValid()) continue;

        FString NodeId;
        if (!NodeObj->TryGetStringField(TEXT("id"), NodeId))
        {
            CreationErrors.Add(TEXT("Node missing 'id' field."));
            continue;
        }

        FString Error;
        UEdGraphNode* NewNode = CreateBPNodeFromJson(Graph, Blueprint, NodeObj, Error);
        if (NewNode)
        {
            NodeMap.Add(NodeId, NewNode);
        }
        else
        {
            CreationErrors.Add(FString::Printf(TEXT("Node '%s': %s"), *NodeId, *Error));
        }
    }

    // Connect pins
    TArray<FString> ConnectionErrors;
    for (auto& ConnVal : ConnectionsArr)
    {
        const TSharedPtr<FJsonObject>& ConnObj = ConnVal->AsObject();
        if (!ConnObj.IsValid()) continue;

        FString SourceNodeId, SourcePinName, TargetNodeId, TargetPinName;
        ConnObj->TryGetStringField(TEXT("source_node"), SourceNodeId);
        ConnObj->TryGetStringField(TEXT("source_pin"), SourcePinName);
        ConnObj->TryGetStringField(TEXT("target_node"), TargetNodeId);
        ConnObj->TryGetStringField(TEXT("target_pin"), TargetPinName);

        UEdGraphNode** SourceNodePtr = NodeMap.Find(SourceNodeId);
        UEdGraphNode** TargetNodePtr = NodeMap.Find(TargetNodeId);

        if (!SourceNodePtr || !*SourceNodePtr)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Source node '%s' not found."), *SourceNodeId));
            continue;
        }
        if (!TargetNodePtr || !*TargetNodePtr)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Target node '%s' not found."), *TargetNodeId));
            continue;
        }

        UEdGraphPin* SourcePin = FindPinByName(*SourceNodePtr, SourcePinName);
        UEdGraphPin* TargetPin = FindPinByName(*TargetNodePtr, TargetPinName);

        if (!SourcePin)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Pin '%s' not found on '%s'."), *SourcePinName, *SourceNodeId));
            continue;
        }
        if (!TargetPin)
        {
            ConnectionErrors.Add(FString::Printf(TEXT("Pin '%s' not found on '%s'."), *TargetPinName, *TargetNodeId));
            continue;
        }

        SourcePin->MakeLinkTo(TargetPin);
    }

    // Layout nodes
    LayoutBPGraphNodes(NodeMap, ConnectionsArr);

    FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);

    // Build result
    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), CreationErrors.Num() == 0 && ConnectionErrors.Num() == 0);
    Result->SetNumberField(TEXT("nodes_created"), NodeMap.Num());
    Result->SetNumberField(TEXT("connections_made"), ConnectionsArr.Num() - ConnectionErrors.Num());

    FString Message = FString::Printf(TEXT("Built graph '%s': %d nodes, %d connections."),
        *GraphName, NodeMap.Num(), ConnectionsArr.Num() - ConnectionErrors.Num());
    if (CreationErrors.Num() > 0 || ConnectionErrors.Num() > 0)
        Message += TEXT(" Some errors occurred.");
    Result->SetStringField(TEXT("message"), Message);

    if (CreationErrors.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ErrArr;
        for (const FString& Err : CreationErrors)
            ErrArr.Add(MakeShareable(new FJsonValueString(Err)));
        Result->SetArrayField(TEXT("creation_errors"), ErrArr);
    }
    if (ConnectionErrors.Num() > 0)
    {
        TArray<TSharedPtr<FJsonValue>> ErrArr;
        for (const FString& Err : ConnectionErrors)
            ErrArr.Add(MakeShareable(new FJsonValueString(Err)));
        Result->SetArrayField(TEXT("connection_errors"), ErrArr);
    }

    // Return node_id -> node_name mapping for reference
    TSharedPtr<FJsonObject> MapObj = MakeShareable(new FJsonObject());
    for (auto& Pair : NodeMap)
    {
        MapObj->SetStringField(Pair.Key, Pair.Value->GetName());
    }
    Result->SetObjectField(TEXT("node_id_to_name"), MapObj);

    return SerializeJsonObj(Result);
}

// ─── CompileBlueprint UFUNCTION ──────────────────────────────────────────────

FString UMCPythonHelper::CompileBlueprint(UBlueprint* Blueprint)
{
    if (!Blueprint)
        return MakeJsonError(TEXT("Invalid Blueprint."));

    FKismetEditorUtilities::CompileBlueprint(Blueprint);

    // Check compile status
    bool bHasError = (Blueprint->Status == BS_Error);
    bool bUpToDate = (Blueprint->Status == BS_UpToDate);

    TSharedPtr<FJsonObject> Result = MakeShareable(new FJsonObject());
    Result->SetBoolField(TEXT("success"), !bHasError);

    FString StatusStr;
    switch (Blueprint->Status)
    {
    case BS_UpToDate: StatusStr = TEXT("UpToDate"); break;
    case BS_Error: StatusStr = TEXT("Error"); break;
    case BS_Dirty: StatusStr = TEXT("Dirty"); break;
    case BS_BeingCreated: StatusStr = TEXT("BeingCreated"); break;
    default: StatusStr = TEXT("Unknown"); break;
    }
    Result->SetStringField(TEXT("status"), StatusStr);
    Result->SetStringField(TEXT("message"),
        bHasError ? TEXT("Blueprint compilation failed. Check the output log for details.")
                  : TEXT("Blueprint compiled successfully."));

    return SerializeJsonObj(Result);
}

// ─── UMG Widget Blueprint Helpers ─────────────────────────────────────────────

namespace
{
    static UClass* FindUMGWidgetClass(const FString& TypeName)
    {
        static const TMap<FString, FString> TypeMap = {
            {TEXT("CanvasPanel"),      TEXT("/Script/UMG.CanvasPanel")},
            {TEXT("TextBlock"),        TEXT("/Script/UMG.TextBlock")},
            {TEXT("Button"),           TEXT("/Script/UMG.Button")},
            {TEXT("Image"),            TEXT("/Script/UMG.Image")},
            {TEXT("HorizontalBox"),    TEXT("/Script/UMG.HorizontalBox")},
            {TEXT("VerticalBox"),      TEXT("/Script/UMG.VerticalBox")},
            {TEXT("Border"),           TEXT("/Script/UMG.Border")},
            {TEXT("Overlay"),          TEXT("/Script/UMG.Overlay")},
            {TEXT("ScrollBox"),        TEXT("/Script/UMG.ScrollBox")},
            {TEXT("SizeBox"),          TEXT("/Script/UMG.SizeBox")},
            {TEXT("CheckBox"),         TEXT("/Script/UMG.CheckBox")},
            {TEXT("EditableText"),     TEXT("/Script/UMG.EditableText")},
            {TEXT("EditableTextBox"),  TEXT("/Script/UMG.EditableTextBox")},
            {TEXT("ProgressBar"),      TEXT("/Script/UMG.ProgressBar")},
            {TEXT("Slider"),           TEXT("/Script/UMG.Slider")},
        };
        const FString* Path = TypeMap.Find(TypeName);
        if (!Path) return nullptr;
        return LoadObject<UClass>(nullptr, **Path);
    }

    static FString UmgErrorJson(const FString& Msg)
    {
        TSharedPtr<FJsonObject> Obj = MakeShared<FJsonObject>();
        Obj->SetBoolField(TEXT("success"), false);
        Obj->SetStringField(TEXT("message"), Msg);
        return SerializeJsonObj(Obj);
    }
}

FString UMCPythonHelper::UmgGetWidgetInfo(UBlueprint* WidgetBP)
{
    UWidgetBlueprint* WB = Cast<UWidgetBlueprint>(WidgetBP);
    if (!WB) return UmgErrorJson(TEXT("Asset is not a WidgetBlueprint."));

    UWidgetTree* WT = WB->WidgetTree;
    if (!WT) return UmgErrorJson(TEXT("Widget tree is null."));

    TSharedPtr<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("success"), true);

    if (WT->RootWidget)
        Root->SetStringField(TEXT("root_widget"), WT->RootWidget->GetName());
    else
        Root->SetField(TEXT("root_widget"), MakeShared<FJsonValueNull>());

    TArray<TSharedPtr<FJsonValue>> WidgetArr;
    WT->ForEachWidget([&](UWidget* W) {
        TSharedPtr<FJsonObject> WObj = MakeShared<FJsonObject>();
        WObj->SetStringField(TEXT("name"), W->GetName());
        WObj->SetStringField(TEXT("type"), W->GetClass()->GetName());
        if (UWidget* Parent = W->GetParent())
            WObj->SetStringField(TEXT("parent"), Parent->GetName());
        WidgetArr.Add(MakeShared<FJsonValueObject>(WObj));
    });

    Root->SetArrayField(TEXT("widgets"), WidgetArr);
    Root->SetNumberField(TEXT("widget_count"), WidgetArr.Num());

    return SerializeJsonObj(Root);
}

FString UMCPythonHelper::UmgAddWidget(UBlueprint* WidgetBP, const FString& WidgetType, const FString& WidgetName, const FString& ParentName)
{
    UWidgetBlueprint* WB = Cast<UWidgetBlueprint>(WidgetBP);
    if (!WB) return UmgErrorJson(TEXT("Asset is not a WidgetBlueprint."));

    UWidgetTree* WT = WB->WidgetTree;
    if (!WT) return UmgErrorJson(TEXT("Widget tree is null."));

    UClass* WidgetClass = FindUMGWidgetClass(WidgetType);
    if (!WidgetClass)
        return UmgErrorJson(FString::Printf(TEXT("Unknown widget type '%s'."), *WidgetType));

    WT->Modify();
    UWidget* NewWidget = WT->ConstructWidget<UWidget>(WidgetClass, FName(*WidgetName));
    if (!NewWidget)
        return UmgErrorJson(FString::Printf(TEXT("Failed to construct widget '%s'."), *WidgetName));

    FString ActualParent;
    bool bIsRoot = false;

    if (!ParentName.IsEmpty())
    {
        UWidget* ParentWidget = WT->FindWidget(FName(*ParentName));
        if (!ParentWidget)
            return UmgErrorJson(FString::Printf(TEXT("Parent widget '%s' not found."), *ParentName));

        UPanelWidget* Panel = Cast<UPanelWidget>(ParentWidget);
        if (!Panel)
            return UmgErrorJson(FString::Printf(TEXT("Parent '%s' is not a panel widget."), *ParentName));

        Panel->AddChild(NewWidget);
        ActualParent = ParentName;
    }
    else if (!WT->RootWidget)
    {
        WT->RootWidget = NewWidget;
        bIsRoot = true;
    }
    else
    {
        UPanelWidget* RootPanel = Cast<UPanelWidget>(WT->RootWidget);
        if (!RootPanel)
            return UmgErrorJson(TEXT("Root widget is not a panel. Specify 'parent_name' explicitly."));
        RootPanel->AddChild(NewWidget);
        ActualParent = RootPanel->GetName();
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("widget_name"), NewWidget->GetName());
    Result->SetStringField(TEXT("widget_type"), WidgetType);
    Result->SetBoolField(TEXT("is_root"), bIsRoot);
    if (!ActualParent.IsEmpty())
        Result->SetStringField(TEXT("parent"), ActualParent);

    return SerializeJsonObj(Result);
}

UWidget* UMCPythonHelper::UmgFindWidget(UBlueprint* WidgetBP, const FString& WidgetName)
{
    UWidgetBlueprint* WB = Cast<UWidgetBlueprint>(WidgetBP);
    if (!WB || !WB->WidgetTree) return nullptr;
    return WB->WidgetTree->FindWidget(FName(*WidgetName));
}

FString UMCPythonHelper::UmgRemoveWidget(UBlueprint* WidgetBP, const FString& WidgetName)
{
    UWidgetBlueprint* WB = Cast<UWidgetBlueprint>(WidgetBP);
    if (!WB) return UmgErrorJson(TEXT("Asset is not a WidgetBlueprint."));

    UWidgetTree* WT = WB->WidgetTree;
    if (!WT) return UmgErrorJson(TEXT("Widget tree is null."));

    UWidget* Widget = WT->FindWidget(FName(*WidgetName));
    if (!Widget)
        return UmgErrorJson(FString::Printf(TEXT("Widget '%s' not found."), *WidgetName));

    WT->Modify();

    UPanelWidget* Parent = Cast<UPanelWidget>(Widget->GetParent());
    if (Parent)
    {
        Parent->RemoveChild(Widget);
    }
    else if (WT->RootWidget && WT->RootWidget->GetName() == WidgetName)
    {
        WT->RootWidget = nullptr;
    }
    else
    {
        return UmgErrorJson(FString::Printf(TEXT("Cannot remove '%s': not attached to a panel or root."), *WidgetName));
    }

    TSharedPtr<FJsonObject> Result = MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("success"), true);
    Result->SetStringField(TEXT("message"), FString::Printf(TEXT("Widget '%s' removed successfully."), *WidgetName));
    return SerializeJsonObj(Result);
}
