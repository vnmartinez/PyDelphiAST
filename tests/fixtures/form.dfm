object MainForm: TMainForm
  Left = 200
  Top = 150
  Caption = 'My Application'
  ClientHeight = 480
  ClientWidth = 640
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -11
  Font.Name = 'Tahoma'
  Font.Style = []
  OldCreateOrder = False
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  PixelsPerInch = 96
  TextHeight = 13
  object Panel1: TPanel
    Left = 0
    Top = 0
    Width = 640
    Height = 41
    Align = alTop
    Caption = ''
    TabOrder = 0
    object Label1: TLabel
      Left = 8
      Top = 12
      Width = 68
      Height = 13
      Caption = 'Search term:'
    end
    object edtSearch: TEdit
      Left = 82
      Top = 8
      Width = 200
      Height = 21
      TabOrder = 0
      OnChange = edtSearchChange
    end
    object btnSearch: TButton
      Left = 292
      Top = 6
      Width = 75
      Height = 25
      Caption = '&Search'
      Default = True
      TabOrder = 1
      OnClick = btnSearchClick
    end
  end
  object lvResults: TListView
    Left = 0
    Top = 41
    Width = 640
    Height = 399
    Align = alClient
    Columns = <
      item
        Caption = 'Name'
        Width = 200
      end
      item
        Caption = 'Value'
        Width = 300
      end>
    ReadOnly = True
    RowSelect = True
    TabOrder = 1
    ViewStyle = vsReport
    OnDblClick = lvResultsDblClick
  end
  object StatusBar1: TStatusBar
    Left = 0
    Top = 440
    Width = 640
    Height = 19
    Panels = <>
    SimpleText = 'Ready'
  end
end
