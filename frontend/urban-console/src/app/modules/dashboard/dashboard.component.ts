import { Component, OnInit, OnDestroy, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PropertyService } from '../../core/services/property.service';
import { KeycloakAuthService } from '../../core/services/keycloak.service';
import { LoadingService } from '../../core/services/loading.service';
import { DashboardStats, PropertySummary, PropertyDetail, Ward } from '../../core/models/property.model';
import { IconComponent } from '../../shared/components/icon/icon.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss'
})
export class DashboardComponent implements OnInit, OnDestroy {
  private propertyService = inject(PropertyService);
  public authService = inject(KeycloakAuthService);
  public loadingService = inject(LoadingService);

  // State Signals
  stats = signal<DashboardStats | null>(null);
  properties = signal<PropertySummary[]>([]);
  wards = signal<Ward[]>([]);
  selectedProperty = signal<PropertyDetail | null>(null);
  isLoading = signal<boolean>(false);
  isSubmitting = signal<boolean>(false);

  // Filters
  searchTerm = '';
  selectedWardId = '';
  selectedStatus = '';

  // Modal controls
  showDetailDrawer = false;
  showRegisterModal = false;

  private tenantChangeHandler = () => {
    this.selectedWardId = '';
    this.searchTerm = '';
    this.selectedStatus = '';
    this.loadStats();
    this.loadWards();
    this.loadProperties();
  };

  // New Property Form Model
  newProperty = {
    ulpin: '',
    survey_number: '',
    plot_number: '',
    total_area_sqyd: 200,
    ward_id: '',
    address: '',
    latitude: 17.985,
    longitude: 79.600,
    building: {
      building_name: '',
      building_type: 'Residential',
      total_floors: 1,
      construction_year: 2024,
      building_permission_no: ''
    },
    unit: {
      ptin: '',
      unit_number: 'G-1',
      floor_number: 0,
      usage_category: 'Residential',
      carpet_area_sqft: 950,
      built_up_area_sqft: 1140,
      occupancy_type: 'Owner',
      annual_rental_value: 36000,
      current_demand_amount: 3600,
      tax_status: 'DUE'
    },
    owner: {
      full_name: '',
      mobile_number: '',
      email: '',
      ownership_share: 100
    }
  };

  ngOnInit(): void {
    this.loadStats();
    this.loadWards();
    this.loadProperties();
    window.addEventListener('urban:tenant-changed', this.tenantChangeHandler);
  }

  ngOnDestroy(): void {
    window.removeEventListener('urban:tenant-changed', this.tenantChangeHandler);
  }

  loadStats(): void {
    this.propertyService.getDashboardStats().subscribe({
      next: (data) => this.stats.set(data),
      error: (err) => console.warn('Could not load stats from backend:', err)
    });
  }

  loadWards(): void {
    this.propertyService.getWards().subscribe({
      next: (data) => {
        this.wards.set(data);
        if (data.length > 0 && !this.newProperty.ward_id) {
          this.newProperty.ward_id = data[0].id;
        }
      },
      error: (err) => console.warn('Could not load wards:', err)
    });
  }

  loadProperties(): void {
    this.isLoading.set(true);
    this.propertyService.getProperties(
      this.searchTerm,
      this.selectedWardId,
      this.selectedStatus
    ).subscribe({
      next: (data) => {
        this.properties.set(data);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.warn('Could not load properties:', err);
        this.isLoading.set(false);
      }
    });
  }

  onSearch(): void {
    this.loadProperties();
  }

  onFilterStatus(status: string): void {
    this.selectedStatus = status;
    this.loadProperties();
  }

  onFilterWard(wardId: string): void {
    this.selectedWardId = wardId;
    this.loadProperties();
  }

  viewDetails(ulpin: string): void {
    this.isLoading.set(true);
    this.propertyService.getPropertyByUlpin(ulpin).subscribe({
      next: (data) => {
        this.selectedProperty.set(data);
        this.showDetailDrawer = true;
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Error fetching property details:', err);
        this.isLoading.set(false);
      }
    });
  }

  closeDrawer(): void {
    this.showDetailDrawer = false;
    this.selectedProperty.set(null);
  }

  openRegisterModal(): void {
    const randomSuffix = Math.floor(1000 + Math.random() * 9000);
    this.newProperty.ulpin = `TG-GWMC-506001-${randomSuffix}`;
    this.newProperty.unit.ptin = `108140${randomSuffix}`;
    this.showRegisterModal = true;
  }

  closeRegisterModal(): void {
    this.showRegisterModal = false;
  }

  submitNewProperty(): void {
    if (!this.newProperty.ulpin || !this.newProperty.owner.full_name || !this.newProperty.address) {
      alert('Please fill in required fields (ULPIN, Owner Name, Address)');
      return;
    }

    this.isSubmitting.set(true);
    this.propertyService.createProperty(this.newProperty).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.closeRegisterModal();
        this.loadStats();
        this.loadProperties();
      },
      error: (err) => {
        this.isSubmitting.set(false);
        alert('Failed to register property: ' + (err.error?.detail || err.message));
      }
    });
  }
}
